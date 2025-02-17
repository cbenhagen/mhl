"""
__author__ = "Patrick Renner, Alexander Sahm"
__copyright__ = "Copyright 2020, Pomfort GmbH"

__license__ = "MIT"
__maintainer__ = "Patrick Renner, Alexander Sahm"
__email__ = "opensource@pomfort.com"
"""

import datetime
import os
import platform

import click
from lxml import etree

from . import logger
from . import errors
from . import ignore
from . import utils
from .ignore import MHLIgnoreSpec
from .__version__ import (
    ascmhl_supported_hashformats,
    ascmhl_folder_name,
    ascmhl_tool_name,
    ascmhl_tool_version,
    ascmhl_default_hashformat,
)
from .generator import MHLGenerationCreationSession
from .hasher import create_filehash, DirectoryHashContext
from .hashlist import MHLCreatorInfo, MHLProcessInfo, MHLTool, MHLProcess
from .history import MHLHistory
from .traverse import post_order_lexicographic


@click.command()
@click.argument("root_path", type=click.Path(exists=True))
# general options
@click.option(
    "--verbose",
    "-v",
    default=False,
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "--hash_format",
    "-h",
    type=click.Choice(ascmhl_supported_hashformats),
    multiple=False,
    default=ascmhl_default_hashformat,
    help="Algorithm",
)
@click.option(
    "--no_directory_hashes",
    "-n",
    default=False,
    is_flag=True,
    help="Skip creation of directory hashes, only reference directories without hash",
)
# subcommands
@click.option(
    "--single_file",
    "-sf",
    multiple=True,
    type=click.Path(exists=True),
    help="Record single file, no completeness check (multiple occurrences possible for adding multiple files",
)
@click.option(
    "ignore_list",
    "--ignore",
    "-i",
    multiple=True,
    help="A single file pattern to ignore.",
)
@click.option(
    "ignore_spec_file",
    "--ignore_spec",
    "-ii",
    type=click.Path(exists=True),
    help="A file containing multiple file patterns to ignore.",
)
def create(root_path, verbose, hash_format, no_directory_hashes, single_file, ignore_list, ignore_spec_file):
    """
    Create a new generation for a folder or file(s)

    \b
    The create command hashes all files given and creates a new generation in the
    mhl-history with records for all hashed files. The command compares the hashes
    against the hashes stored in previous generations if available.
    """
    # distinguish different behavior for entire folder vs single files
    if single_file is not None and len(single_file) > 0:
        create_for_single_files_subcommand(root_path, verbose, hash_format, no_directory_hashes, single_file)
        return
    create_for_folder_subcommand(
        root_path, verbose, hash_format, no_directory_hashes, single_file, ignore_list, ignore_spec_file
    )
    return


def create_for_folder_subcommand(
    root_path, verbose, hash_format, no_directory_hashes, single_file, ignore_list=None, ignore_spec_file=None
):
    # command formerly known as "seal"
    """
    Creates a new generation with all files in a folder hierarchy.

    ROOT_PATH: the root path to use for the asc mhl history

    All files are hashed and will be compared to previous records in the `asc-mhl` folder if they exists.
    The command finds files that are registered in the `asc-mhl` folder but that are missing in the file system.
    Files that are existent in the file system but are not registered in the `asc-mhl` folder yet, are registered
    as new entries in the newly created generation(s).
    """
    logger.verbose_logging = verbose

    if not os.path.isabs(root_path):
        root_path = os.path.join(os.getcwd(), root_path)

    logger.verbose(f"Sealing folder at path: {root_path} ...")

    existing_history = MHLHistory.load_from_path(root_path)

    # we collect all paths we expect to find first and remove every path that we actually found while
    # traversing the file system, so this set will at the end contain the file paths not found in the file system
    not_found_paths = existing_history.set_of_file_paths()

    # create the ignore specification
    ignore_spec = ignore.MHLIgnoreSpec(existing_history.latest_ignore_patterns(), ignore_list, ignore_spec_file)

    # start a verification session on the existing history
    session = MHLGenerationCreationSession(existing_history, ignore_spec)

    num_failed_verifications = 0
    # store the directory hashes of sub folders so we can use it when calculating the hash of the parent folder
    dir_hash_mappings = {}

    for folder_path, children in post_order_lexicographic(root_path, session.ignore_spec.get_path_spec()):
        # generate directory hashes
        dir_hash_context = None
        if not no_directory_hashes:
            dir_hash_context = DirectoryHashContext(hash_format)
        for item_name, is_dir in children:
            file_path = os.path.join(folder_path, item_name)
            not_found_paths.discard(file_path)
            if is_dir:
                if not dir_hash_context:
                    continue
                hash_string = dir_hash_mappings.pop(file_path)
            else:
                hash_string, success = seal_file_path(existing_history, file_path, hash_format, session)
                if not success:
                    num_failed_verifications += 1
            if dir_hash_context:
                dir_hash_context.append_hash(hash_string, item_name)
        dir_hash = None
        if dir_hash_context:
            dir_hash = dir_hash_context.final_hash_str()
            dir_hash_mappings[folder_path] = dir_hash
        modification_date = datetime.datetime.fromtimestamp(os.path.getmtime(folder_path))
        session.append_directory_hash(folder_path, modification_date, hash_format, dir_hash)

    commit_session(session)

    exception = test_for_missing_files(not_found_paths, root_path, ignore_spec)
    if num_failed_verifications > 0:
        exception = errors.VerificationFailedException()

    if exception:
        raise exception


def create_for_single_files_subcommand(root_path, verbose, hash_format, no_directory_hashes, single_file):
    # command formerly known as "record"
    """
    Creates a new generation with the given file(s) or folder(s).

    \b
    ROOT_PATH: the root path to use for the asc mhl history
    single_file: one or multiple paths to files or folders to be recorded

    All files that are specified or the files inside a specified folder are hashed and will be compared
    to previous records in the `asc-mhl` folder if they are recorded in the history already.

    The following files will not be handled by this command:

    \b
    * files that are referenced in the existing ascmhl history but not specified as input
    * files that are neither referenced in the history nor specified as input
    """
    logger.verbose_logging = verbose

    if not os.path.isabs(root_path):
        root_path = os.path.join(os.getcwd(), root_path)

    assert len(single_file) != 0

    existing_history = MHLHistory.load_from_path(root_path)
    # start a creation session on the existing history
    session = MHLGenerationCreationSession(existing_history)

    num_failed_verifications = 0
    for path in single_file:
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        if os.path.isdir(path):
            for folder_path, children in post_order_lexicographic(path, session.ignore_spec.get_path_spec()):
                for item_name, is_dir in children:
                    file_path = os.path.join(folder_path, item_name)
                    if is_dir:
                        continue
                    _, success = seal_file_path(existing_history, file_path, hash_format, session)
                    if not success:
                        num_failed_verifications += 1
        else:
            _, success = seal_file_path(existing_history, path, hash_format, session)
            if not success:
                num_failed_verifications += 1

    commit_session(session)

    if num_failed_verifications > 0:
        raise errors.VerificationFailedException()


@click.command()
@click.argument("root_path", type=click.Path(exists=True))
@click.option(
    "--verbose",
    "-v",
    default=False,
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "ignore_list",
    "--ignore",
    "-i",
    multiple=True,
    help="A single file pattern to ignore.",
)
@click.option(
    "ignore_spec_file",
    "--ignore_spec",
    "-ii",
    type=click.Path(exists=True),
    help="A file containing multiple file patterns to ignore.",
)
def verify(root_path, verbose, ignore_list, ignore_spec_file):
    """
    Verify a folder, single file(s), or a directory hash

    \b
    The verify command is used to check files in the file system with records in
    the ASC MHL history. All given files are hashed and hash values are compared
    against hash values stored in the ASC MHL history. Missing files or additional
    files in the file system are reported as errors. No new ASC MHL file /
    generation is created.
    """
    # TODO distinguish different behavior
    verify_entire_folder_against_full_history_subcommand(root_path, verbose, ignore_list, ignore_spec_file)
    return


def verify_entire_folder_against_full_history_subcommand(root_path, verbose, ignore_list=None, ignore_spec_file=None):
    # command formerly known as "check"
    """
    Checks MHL hashes from all generations against all file hashes.

    ROOT_PATH: the root path to use for the asc mhl history

    Traverses through the content of a folder, hashes all found files and compares ("verifies") the hashes
    against the records in the asc-mhl folder. The command finds all files that are existent in the file system
    but are not registered in the `asc-mhl` folder yet, and all files that are registered in the `asc-mhl` folder
    but that are missing in the file system.
    """
    logger.verbose_logging = verbose

    if not os.path.isabs(root_path):
        root_path = os.path.join(os.getcwd(), root_path)

    logger.verbose(f"check folder at path: {root_path}")

    existing_history = MHLHistory.load_from_path(root_path)

    if len(existing_history.hash_lists) == 0:
        raise errors.NoMHLHistoryException(root_path)

    # we collect all paths we expect to find first and remove every path that we actually found while
    # traversing the file system, so this set will at the end contain the file paths not found in the file system
    not_found_paths = existing_history.set_of_file_paths()

    num_failed_verifications = 0
    num_new_files = 0

    ignore_spec = ignore.MHLIgnoreSpec(existing_history.latest_ignore_patterns(), ignore_list, ignore_spec_file)

    for folder_path, children in post_order_lexicographic(root_path, ignore_spec.get_path_spec()):
        for item_name, is_dir in children:
            file_path = os.path.join(folder_path, item_name)
            not_found_paths.discard(file_path)
            relative_path = existing_history.get_relative_file_path(file_path)
            history, history_relative_path = existing_history.find_history_for_path(relative_path)
            if is_dir:
                # TODO: find new directories here
                continue

            # check if there is an existing hash in the other generations and verify
            original_hash_entry = history.find_original_hash_entry_for_path(history_relative_path)

            # in case there is no original hash entry continue
            if original_hash_entry is None:
                logger.error(f"found new file {relative_path}")
                num_new_files += 1
                continue

            # create a new hash and compare it against the original hash entry
            current_hash = create_filehash(original_hash_entry.hash_format, file_path)
            if original_hash_entry.hash_string == current_hash:
                logger.verbose(f"verification of file {relative_path}: OK")
            else:
                logger.error(
                    f"ERROR: hash mismatch        for {relative_path} "
                    f"old {original_hash_entry.hash_format}: {original_hash_entry.hash_string}, "
                    f"new {original_hash_entry.hash_format}: {current_hash}"
                )
                num_failed_verifications += 1

    exception = test_for_missing_files(not_found_paths, root_path, ignore_spec)
    if num_new_files > 0:
        exception = errors.NewFilesFoundException()
    if num_failed_verifications > 0:
        exception = errors.VerificationFailedException()

    if exception:
        raise exception


# TODO def verify_single_file_subcommand(root_path, verbose):
# TODO def verify_directory_hash_subcommand(root_path, verbose):


@click.command()
@click.argument("root_path", type=click.Path(exists=True))
@click.option(
    "--verbose",
    "-v",
    default=False,
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "ignore_list",
    "--ignore",
    "-i",
    multiple=True,
    help="A single file pattern to ignore.",
)
@click.option(
    "ignore_spec_file",
    "--ignore_spec",
    "-ii",
    type=click.Path(exists=True),
    help="A file containing multiple file patterns to ignore.",
)
def diff(root_path, verbose, ignore_list, ignore_spec_file):
    """
    Diff an entire folder structure

    \b
    The diff command is used to quickly compare files in the file system with
    records in the ASC MHL history. In comparison to the verify command, no
    hash values are created and compared. Missing files or additional files
    in the file system are reported as errors. No new ASC MHL file / generation
    is created.
    """
    diff_entire_folder_against_full_history_subcommand(root_path, verbose, ignore_list, ignore_spec_file)
    return


def diff_entire_folder_against_full_history_subcommand(root_path, verbose, ignore_list=None, ignore_spec_file=None):
    """
    Checks MHL hashes from all generations against all file hash entries.

    ROOT_PATH: the root path to use for the asc mhl history

    Traverses through the content of a folder. The command finds all files that are existent in the file system
    but are not registered in the `asc-mhl` folder yet, and all files that are registered in the `asc-mhl` folder
    but that are missing in the file system.
    """
    logger.verbose_logging = verbose

    if not os.path.isabs(root_path):
        root_path = os.path.join(os.getcwd(), root_path)

    logger.verbose(f"check folder at path: {root_path}")

    existing_history = MHLHistory.load_from_path(root_path)

    if len(existing_history.hash_lists) == 0:
        raise errors.NoMHLHistoryException(root_path)

    # we collect all paths we expect to find first and remove every path that we actually found while
    # traversing the file system, so this set will at the end contain the file paths not found in the file system
    not_found_paths = existing_history.set_of_file_paths()
    num_failed_verifications = 0
    num_new_files = 0

    ignore_spec = ignore.MHLIgnoreSpec(existing_history.latest_ignore_patterns(), ignore_list, ignore_spec_file)

    for folder_path, children in post_order_lexicographic(root_path, ignore_spec.get_path_spec()):
        for item_name, is_dir in children:
            file_path = os.path.join(folder_path, item_name)
            not_found_paths.discard(file_path)
            relative_path = existing_history.get_relative_file_path(file_path)
            history, history_relative_path = existing_history.find_history_for_path(relative_path)
            if is_dir:
                # TODO: find new directories here
                continue

            # check if there is an existing hash in the other generations and verify
            original_hash_entry = history.find_original_hash_entry_for_path(history_relative_path)

            # in case there is no original hash entry continue
            if original_hash_entry is None:
                logger.error(f"found new file {relative_path}")
                num_new_files += 1
                continue

    exception = test_for_missing_files(not_found_paths, root_path, ignore_spec)
    if num_new_files > 0:
        exception = errors.NewFilesFoundException()
    if num_failed_verifications > 0:
        exception = errors.VerificationFailedException()

    if exception:
        raise exception


@click.command()
@click.option(
    "--verbose",
    "-v",
    default=False,
    is_flag=True,
    help="Verbose output",
)
# subcommands
@click.option(
    "--single_file",
    "-sf",
    multiple=True,
    type=click.Path(exists=True),
    help="Info for single file",
)
# options
@click.option(
    "--root_path",
    "-rp",
    default="",
    type=click.STRING,
    help="Root path for history",
)
def info(verbose, single_file, root_path):
    """
    Prints information from the ASC MHL history

    \b
    """
    if single_file is not None and len(single_file) > 0:
        if root_path == "":
            current_dir = os.path.dirname(os.path.abspath(single_file[0]))
            while current_dir != "/" and current_dir != "":
                asc_mhl_folder_path = os.path.join(current_dir, ascmhl_folder_name)
                if os.path.exists(asc_mhl_folder_path):
                    root_path = current_dir
                    break
                current_dir = os.path.dirname(current_dir)
        if root_path == "":
            raise errors.NoMHLHistoryExceptionForPath(single_file[0])
        else:
            info_for_single_file(root_path, verbose, single_file)
        return
    return


def info_for_single_file(root_path, verbose, single_file):
    """
    ROOT_PATH: the root path to use for the asc mhl history (optional)
    """

    logger.verbose_logging = verbose

    if not os.path.isabs(root_path):
        root_path = os.path.join(os.getcwd(), root_path)

    logger.info(f"Info with history at path: {root_path}")

    existing_history = MHLHistory.load_from_path(root_path)

    if len(existing_history.hash_lists) == 0:
        raise errors.NoMHLHistoryException(root_path)

    for path in single_file:
        relative_path = existing_history.get_relative_file_path(os.path.abspath(path))
        logger.info(f"{relative_path}:")
        for hash_list in existing_history.hash_lists:
            media_hash = hash_list.find_media_hash_for_path(relative_path)
            if media_hash is None:
                continue
            for hash_entry in media_hash.hash_entries:
                if logger.verbose_logging == True:
                    absolutePath = os.path.join(hash_list.get_root_path(), media_hash.path)
                    creatorInfo = hash_list.creator_info.summary()
                    processInfo = hash_list.process_info.summary()
                    logger.info(
                        f"  Generation {hash_list.generation_number} ({hash_list.creator_info.creation_date})"
                        f" {hash_entry.hash_format}: {hash_entry.hash_string} ({hash_entry.action}) \n"
                        f"    {absolutePath}\n"
                        f"    {creatorInfo}\n"
                        f"    {processInfo}"
                    )
                else:
                    logger.info(
                        f"  Generation {hash_list.generation_number} ({hash_list.creator_info.creation_date})"
                        f" {hash_entry.hash_format}: {hash_entry.hash_string} ({hash_entry.action})"
                    )


@click.command()
@click.argument("file_path", type=click.Path(exists=True))
def xsd_schema_check(file_path):
    """
    Checks a .mhl file against the xsd schema definition

    \b
    The xsd-schema-check command validates a given ASC MHL file against the XML
    XSD. This command can be used to ensure the creation of syntactically valid
    ASC MHL files, for example during implementation of tools creating ASC MHL
    files.
    """

    xsd_path = "xsd/ASCMHL.xsd"
    xsd = etree.XMLSchema(etree.parse(xsd_path))

    # pass a file handle to support the fake file system used in the tests
    file = open(file_path, "rb")
    result = xsd.validate(etree.parse(file))

    if result:
        logger.info(f"validated: {file_path}")
    else:
        logger.error(f"ERROR: {file_path} didn't validate against XSD!")
        logger.info(f"Issues:\n{xsd.error_log}")
        raise errors.VerificationFailedException


# TODO should be part of the `verify -dh` subcommand
@click.command()
@click.argument("root_path", type=click.Path(exists=True))
@click.option(
    "--verbose",
    "-v",
    default=False,
    is_flag=True,
    help="Print all directory hashes of sub directories",
)
@click.option(
    "--hash_format",
    "-h",
    type=click.Choice(ascmhl_supported_hashformats),
    multiple=False,
    default=ascmhl_default_hashformat,
    help="Algorithm",
)
@click.option(
    "ignore_list",
    "--ignore",
    "-i",
    multiple=True,
    help="A single file pattern to ignore.",
)
@click.option(
    "ignore_spec_file",
    "--ignore_spec",
    "-ii",
    type=click.Path(exists=True),
    help="A file containing multiple file patterns to ignore.",
)
def directory_hash(root_path, verbose, hash_format, ignore_list, ignore_spec_file):
    """
    [TMP] Creates the directory hash of a given folder
    """
    if not os.path.isabs(root_path):
        root_path = os.path.join(os.getcwd(), root_path)

    # store the directory hashes of sub folders so we can use it when calculating the hash of the parent folder
    dir_hash_mappings = {}

    ignore_spec = ignore.MHLIgnoreSpec(None, ignore_list, ignore_spec_file)

    for folder_path, children in post_order_lexicographic(root_path, ignore_spec.get_path_spec()):
        dir_hash_context = DirectoryHashContext(hash_format)
        for item_name, is_dir in children:
            item_path = os.path.join(folder_path, item_name)
            if is_dir:
                if not dir_hash_context:
                    continue
                hash_string = dir_hash_mappings.pop(item_path)
            else:
                hash_string = create_filehash(hash_format, item_path)
            dir_hash_context.append_hash(hash_string, item_name)
        dir_hash = dir_hash_context.final_hash_str()
        dir_hash_mappings[folder_path] = dir_hash
        if folder_path == root_path:
            logger.info(f"  calculated root hash: {hash_format}: {dir_hash}")
        elif verbose:
            logger.info(f"directory hash for: {folder_path} {hash_format}: {dir_hash}")


def test_for_missing_files(not_found_paths, root_path, ignore_spec: MHLIgnoreSpec = MHLIgnoreSpec()):
    ignore_path_spec = ignore_spec.get_path_spec()
    # update to exclude our ignored files
    not_found_paths = [x for x in not_found_paths if not ignore_path_spec.match_file(x)]
    if len(not_found_paths) == 0:
        return None
    # test our not_found_paths against our ignore spec to ensure these weren't explicitly ignored.
    logger.error(f"ERROR: {len(not_found_paths)} missing file(s):")
    for path in not_found_paths:
        logger.error(f"  {os.path.relpath(path, root_path)}")
    return errors.CompletenessCheckFailedException()


def commit_session(session):
    creator_info = MHLCreatorInfo()
    creator_info.tool = MHLTool(ascmhl_tool_name, ascmhl_tool_version)
    creator_info.creation_date = utils.datetime_now_isostring()
    creator_info.host_name = platform.node()
    process_info = MHLProcessInfo()
    process_info.process = MHLProcess("in-place")
    session.commit(creator_info, process_info)


def seal_file_path(existing_history, file_path, hash_format, session) -> (str, bool):
    relative_path = existing_history.get_relative_file_path(file_path)
    file_size = os.path.getsize(file_path)
    file_modification_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))

    # find in the according child history the already available hash formats
    existing_child_history, existing_history_relative_path = existing_history.find_history_for_path(relative_path)
    existing_hash_formats = existing_child_history.find_existing_hash_formats_for_path(existing_history_relative_path)

    # in case there is no hash in the required format to use yet, we need to verify also against
    # one of the existing hash formats, we for simplicity use always the first hash format in this example
    # but one could also use a different one if desired
    success = True
    if len(existing_hash_formats) > 0 and hash_format not in existing_hash_formats:
        existing_hash_format = existing_hash_formats[0]
        hash_in_existing_format = create_filehash(existing_hash_format, file_path)
        # FIXME: test what happens if the existing hash verification fails in other format fails
        # should we then really create two entries
        success &= session.append_file_hash(
            file_path, file_size, file_modification_date, existing_hash_format, hash_in_existing_format
        )
    current_format_hash = create_filehash(hash_format, file_path)
    # in case the existing hash verification failed we don't want to add the current format hash to the generation
    # but we need to return it for directory hash creation
    if not success:
        return current_format_hash, False
    success &= session.append_file_hash(file_path, file_size, file_modification_date, hash_format, current_format_hash)
    return current_format_hash, success
