from src.util.datetime import datetime_now_filename_string
from src.mhl.hash import create_filehash
from src.util import logger
from src.util import matches_prefixes
from src.util.constants import filename_ignore_prefixes
import os
import re
import click


class HashListFolderManager:
    """class for managing an asc-mhl folder with MHL files

    is used to write a ready XML string to a new MHL file, and also includes lots of helper functions

    member variables:
    folderpath -- path to the enclosing folder (not the asc-mhl folder itself, but one up)
    """

    ascmhl_folder_name = "asc-mhl"
    ascmhl_file_extension = ".ascmhl"
    ascmhl_hash_file_extension = ".hash"
    ascmhl_signature_file_extension = ".signature"
    ascmhl_chainfile_name = "chain.txt"
    hashformat_for_ascmhl_files = 'xxhash'

    def __init__(self, folderpath):
        # TODO: we shouldn't be setting verbosity on these classes. reference context for value when needed
        self.verbose = click.get_current_context().obj.verbose
        # TODO: what was this check for? click should handle path anomolies since we used the special "path" type.
        if not folderpath[len(folderpath):1] == os.path.sep:
            folderpath = folderpath + os.path.sep
        self.folderpath = folderpath

        self.generation_hashes = []
        self.read_generation_hashes_and_signatures()

    def ascmhl_folder_path(self):
        """absolute path of the asc-mhl folder"""
        path = os.path.join(os.path.normpath(self.folderpath), HashListFolderManager.ascmhl_folder_name)
        return path

    def ascmhl_chainfile_path(self):
        """absolute path of the chain file"""
        path = os.path.join(self.ascmhl_folder_path(), HashListFolderManager.ascmhl_chainfile_name)
        return path

    def ascmhl_folder_exists(self):
        return os.path.exists(self.ascmhl_folder_path())

    def ascmhl_folder_exists_above_up_to_but_excluding(self, rootpath):
        """finds out if self is embedded within a folder that itself has an asc-mhl folder"""
        if os.path.relpath(self.folderpath, rootpath) is None:
            return False
        #path = os.path.dirname(os.path.normpath(self.folderpath))
        path = os.path.normpath(self.folderpath)
        rootpath = os.path.normpath(rootpath)
        while path != rootpath:
            ascmhl_path = os.path.join(path, self.ascmhl_folder_name)
            if os.path.exists(ascmhl_path):
                return True
            path = os.path.dirname(path)
        return False

    def queried_ascmhl_filename(self, generation_number):
        ascmhl = self._ascmhl_files(generation_number)
        if 'queried_filename' in ascmhl:
            return ascmhl['queried_filename']
        else:
            return None

    def earliest_ascmhl_generation_number(self) -> int:
        ascmhl = self._ascmhl_files()
        return ascmhl['earliest_generation_number']

    def earliest_ascmhl_filename(self):
        ascmhl = self._ascmhl_files()
        return ascmhl['earliest_filename']

    def latest_ascmhl_generation_number(self) -> int:
        ascmhl = self._ascmhl_files()
        return ascmhl['latest_generation_number']

    def latest_ascmhl_filename(self):
        ascmhl = self._ascmhl_files()
        return ascmhl['latest_filename']

    def _ascmhl_files(self, query_generation_number=None):
        """find all MHL files in the asc-mhl folder, returns information about found generations

        arguments:
        query_generation_number -- find additional information about a specific generation
        """
        ascmhl_folder_path = self.ascmhl_folder_path()
        if ascmhl_folder_path is None:
            return None
        else:
            queried_filename = None
            queried_generation_number = 0
            earliest_filename = None
            lowest_generation_number = 1000000
            latest_filename = None
            highest_generation_number = 0
            for root, directories, filenames in os.walk(ascmhl_folder_path):
                for filename in filenames:
                    if filename.endswith(HashListFolderManager.ascmhl_file_extension):
                        # A002R2EC_2019-06-21_082301_0005.ascmhl
                        parts = re.findall(r'(.*)_(.+)_(.+)_(\d+)\.ascmhl', filename)
                        if parts.__len__() == 1 and parts[0].__len__() == 4:
                            generation_number = int(parts[0][3])
                            if query_generation_number == generation_number:
                                queried_generation_number = generation_number
                                queried_filename = filename
                            if lowest_generation_number > generation_number:
                                lowest_generation_number = generation_number
                                earliest_filename = filename
                            if highest_generation_number < generation_number:
                                highest_generation_number = generation_number
                                latest_filename = filename
                        else:
                            logger.error(f'name of ascmhl file {filename} doesnt conform to naming convention')
            result_tuple = {'earliest_filename': earliest_filename,
                            'earliest_generation_number': lowest_generation_number,
                            'latest_filename': latest_filename,
                            'latest_generation_number': highest_generation_number}

            if queried_filename is not None:
                result_tuple['queried_filename'] = queried_filename
                result_tuple['queried_generation_number'] = queried_generation_number

            return result_tuple

    def path_for_ascmhl_file(self, filename):
        if filename is None:
            return None
        else:
            path = os.path.join(self.folderpath, HashListFolderManager.ascmhl_folder_name, filename)
            return path

    def path_for_ascmhl_generation_number(self, generation_number):
        if generation_number is None:
            return None
        else:
            filename = self.queried_ascmhl_filename(generation_number)
            if filename is None:
                return None
            path = os.path.join(self.folderpath, HashListFolderManager.ascmhl_folder_name, filename)
            return path

    def new_ascmhl_filename(self):
        date_string = datetime_now_filename_string()
        index = self.latest_ascmhl_generation_number() + 1
        return os.path.basename(os.path.normpath(self.folderpath)) + "_" + date_string + "_" + str(index).zfill(
            4) + ".ascmhl"

    def path_for_new_ascmhl_file(self):
        filename = self.new_ascmhl_filename()
        if filename is not None:
            return self.path_for_ascmhl_file(filename)

    def path_for_generation_hash_file(self, generation):
        if generation is not None:
            return os.path.join(self.folderpath, HashListFolderManager.ascmhl_folder_name,
                                generation.hash_filename())
        else:
            return None

    def path_for_generation_signature_file(self, generation):
        if generation is not None:
            return os.path.join(self.folderpath, HashListFolderManager.ascmhl_folder_name,
                                generation.signature_filename())
        else:
            return None

    def write_ascmhl(self, xml_string, signature_identifier=None, private_key_filepath=None):
        """writes a given XML string into a new MHL file"""
        filepath = self.path_for_new_ascmhl_file()
        if filepath is not None:
            logger.info(f'writing {filepath}')
            with open(filepath, 'wb') as file:
                # FIXME: check if file could be created
                file.write(xml_string.encode('utf8'))

            if private_key_filepath is None:
                generation = HashListGeneration.\
                    with_new_ascmhl_file(self.latest_ascmhl_generation_number(),
                                         filepath,
                                         HashListFolderManager.hashformat_for_ascmhl_files)
            else:
                generation = HashListGeneration.\
                    with_new_ascmhl_file_and_signature(self.latest_ascmhl_generation_number(),
                                                       filepath,
                                                       HashListFolderManager.hashformat_for_ascmhl_files,
                                                       signature_identifier, private_key_filepath)

            self.add_generation_file(generation)

            return filepath

    def file_is_in_ascmhl_folder(self, filepath):
        ascmhl_folder_path = self.ascmhl_folder_path()
        if ascmhl_folder_path is None:
            return False
        else:
            return filepath.startswith(self.ascmhl_folder_path())


    def add_generation_file(self, generation):
        """ creates a generation file in the asc-mhl folder
        """

        # TODO sanity checks
        # - if generation is already part of self.generations
        # - if generation number is sequential

        # immediately write to file
        if generation.is_signed():
            logger.info(
                f'creating generation hash file for \"{generation.ascmhl_filename}\" with signature for '
                f'{generation.signature_identifier} to chain file')
        else:
            logger.info(
                f'creating generation hash file for \"{generation.ascmhl_filename}\"')

        with open(self.path_for_generation_hash_file(generation), 'w+') as file:
            file.write(generation.line_for_hash_file() + "\n")

        # FIXME: check if file could be created

        # …and store here
        # FIXME: only if successfully written to file
        generation.chain = self
        self.generation_hashes.append(generation)

        # FIXME: return success

    def verify_all_generations(self):
        """verifies asc-mhl files of all listed generations in chain file

        result value:
        0 - everything ok
        >0 - number of verification failures
        """

        # TODO sanity checks
        # - if generation numbers are sequential and complete
        # - check if all files exist

        if self.generation_hashes is not None and self.generation_hashes.__len__() > 0:
            logger.info(f'verifying all ascmhl files in {self.ascmhl_folder_path()}')

        number_of_failures = 0
        for generation in self.generation_hashes:
            result = generation.verify_hash()
            if result is False:
                number_of_failures = number_of_failures + 1

        return number_of_failures

    def read_generation_hashes_and_signatures(self):

        for root, directories, filenames in os.walk(self.ascmhl_folder_path()):
            for filename in filenames:

                if matches_prefixes(filename, filename_ignore_prefixes) is False:
                    parts = re.findall(r'(.*)_(.+)_(.+)_(\d+)\.ascmhl(.*)', filename)
                    if parts.__len__() == 1 and (parts[0].__len__() == 4 or parts[0].__len__() == 5):
                        generation_number = int(parts[0][3])

                    else:
                        logger.error(f'name of file {filename} doesnt conform to naming convention')

                    if filename.endswith(HashListFolderManager.ascmhl_hash_file_extension):
                        # A002R2EC_2019-06-21_082301_0005.ascmhl.hash
                        hash_file_path = os.path.join(os.path.normpath(self.ascmhl_folder_path()), filename)
                        generation = HashListGeneration.with_hash_file(hash_file_path, generation_number)
                        if generation is not None:
                            self.generation_hashes.append(generation)

                   # if filename.endswith(HashListFolderManager.ascmhl_hash_file_extension):
                        # A002R2EC_2019-06-21_082301_0005.ascmhl.signature


                    # for each asc-mhl file read .hash and .signature file

                    # fill generation and append to self.generation_hashes




class HashListGeneration:
    """class for representing one generation with the hash of the asc-mhl file

    member variables:
    generation_number -- integer, -1 means invalid
    ascmhl_filename --
    hashformat --
    hash_string --
    signature_identifier -- opt, used to find public key
    signature -- opt, base64 encoded
    chain -- needed for absolute path resolution
    """

    def __init__(self):

        # line string examples:
        # 0001 A002R2EC_2019-10-08_100916_0001.ascmhl SHA1: 9e9302b3d7572868859376f0e5802b87bab3199e
        # 0001 A002R2EC_2019-10-08_100916_0001.ascmhl SHA1: 9e9302b3d7572868859376f0e5802b87bab3199e bob@example.com enE9miWg6gKQQpYYzYzNVdrOrE58jnNbnqBW/J44g9jniMej7tjqhwezWd7PbfE5T+qcNx0VEetVSNiMllgGPLNcI1lw/Io/rS1NgVO13sCHd4BOPXlux2sUBuZWQliP9WFuuomtDulZyQaaSc1AOQ1YjKPuGIDoLlwvS7KXMMg=

        self.generation_number = -1  # integer, -1 means invalid
        self.ascmhl_filename = None
        self.ascmhl_folder_path = None
        self.hashformat = None
        self.hash_string = None
        self.signature_identifier = None  # opt, used to find public key
        self.signature = None  # opt, base64 encoded
        self.chain = None;

    @classmethod
    def with_hash_file(cls, hash_file_path, generation_number):
        """ creates a HashListGeneration object from a .hash file
        """
        generation = None

        with open(hash_file_path, 'r') as hash_file:
            line = hash_file.read().replace('\n', '')

            parts = re.findall(r'(.+)\((.+)\)= (.+)', line)
            if parts.__len__() == 1 and parts[0].__len__() == 3:
                generation = cls()

                generation.generation_number = generation_number
                generation.ascmhl_filename = parts[0][1]
                generation.hashformat = parts[0][0]
                generation.hash_string = parts[0][2]

                generation.ascmhl_folder_path = os.path.dirname(os.path.normpath(hash_file_path))

            else:
                logger.error("cannot read line \"{line}\"")

        # TODO sanity checks

        return generation

    @classmethod
    def with_new_ascmhl_file(cls, generation_number, filepath, hashformat):
        """ hashes ascmhl file and creates new, filled Generation object
        """

        # TODO check if ascmhl file exists

        generation = cls()

        generation.generation_number = generation_number
        generation.ascmhl_filename = os.path.basename(os.path.normpath(filepath))
        generation.hashformat = hashformat

        # TODO somehow pass in xxattr flag from context ?
        generation.hash_string = create_filehash(filepath, hashformat)

        return generation

    @classmethod
    def with_new_ascmhl_file_and_signature(cls, generation_number, filepath, hashformat,
                                           signature_identifier, private_key_filepath):
        """ hashes ascmhl file, signs it, and creates new, filled Generation object
        """

        generation = HashListGeneration.with_new_ascmhl_file(generation_number, filepath, hashformat)

        signature_string = sign_hash(generation.hash_string, private_key_filepath)

        generation.signature_identifier = signature_identifier
        generation.signature = signature_string

        return generation

    def hash_filename(self):
        return f'{self.ascmhl_filename}{HashListFolderManager.ascmhl_hash_file_extension}'

    def signature_filename(self):
        return f'{self.ascmhl_filename}{HashListFolderManager.ascmhl_signature_file_extension}'

    def is_signed(self):
        return self.signature_identifier is not None and self.signature is not None

    def line_for_hash_file(self):
        """creates the content of the hash file for a generation / ASC-MHL file
        """
        result_string = f'{self.hashformat}({self.ascmhl_filename})= {self.hash_string}\n'

        if self.is_signed():
            result_string = result_string + " " + self.signature_identifier + " " + self.signature

        return result_string

    def line_for_signature_file(self):
        """creates the content of the signature file for a generation / ASC-MHL file
        """
        result_string = f'{self.hashformat}({self.ascmhl_filename})= {self.hash_string}\n'

        if self.is_signed():
            result_string = result_string + "\n" + self.signature_identifier + "\n" + self.signature

        return result_string

    def verify(self, public_key_filepath=None):
        """verifies hash and signature (if available) of generation

        paramters:
        public_key_filepath - path to pem file with signer's public key (needs to be found via self.signature_identifier)

        result value:
        True - everything ok
        False - verification of hash or signature failed
        """

        result = self.verify_hash()

        if result is False:
            return False

        if self.is_signed():
            if public_key_filepath is None:
                logger.error("public key needed for verifying signature of generation {self.generation_number}")
                result = False
            else:
                result = self.verify_signature(public_key_filepath)

        return result

    def verify_hash(self):
        """verifies the asc-mhl file of a generation against available hash

        result value:
        True - everything ok
        False - verification failed
        """

        ascmhl_file_path = os.path.join(self.ascmhl_folder_path, self.ascmhl_filename)

        # TODO somehow pass in xxattr flag from context ?
        current_filehash = create_filehash(ascmhl_file_path , self.hashformat)

        if current_filehash != self.hash_string:
            logger.error(f'hash mismatch for {self.ascmhl_filename} '
                         f'old {self.hashformat}: {self.hash_string}, '
                         f'new {self.hashformat}: {current_filehash}')
            self.log_chain_generation(True, 'failed')
            return False
        else:
            self.log_chain_generation(False, 'verified')
            return True

        # digest again in order to compare hashes
        # $ openssl dgst -sha1 self.ascmhl_filename

        # return result of hash comparison:
        # return (digest_hash == self.hash_string)

    def verify_signature(self, public_key_filepath):
        """verifies the signature against  available hash

        paramters:
        public_key_filepath - path to pem file with signer's public key (needs to be found via self.signature_identifier)

        result value:
        True - everything ok
        False - verification of signature failed
        """

        signature_hash = check_signature(self.signature, public_key_filepath)

        # return result of hash comparison:
        if signature_hash != self.hash_string:
            logger.error(f'signature verification failed for {self.ascmhl_filename} with '
                         f'public key at {public_key_filepath}')
            self.log_chain_generation(True, 'sig failed')
            return False
        else:
            self.log_chain_generation(False, 'sig ok')
            return True


    def log_chain_generation(self, failed, action):
        indicator = " "
        if failed:
            indicator = "!"

        if self.is_signed():
            logger.info("{0} {1}: {2} {3}: {4} (signed by {5})".format(indicator,
                                                                       self.hashformat.rjust(6),
                                                                       self.hash_string.ljust(32),
                                                                       action.ljust(10),
                                                                       self.ascmhl_filename,
                                                                       self.signature_identifier))
        else:
            logger.info("{0} {1}: {2} {3}: {4}".format(indicator,
                                                       self.hashformat.rjust(6),
                                                       self.hash_string.ljust(32),
                                                       action.ljust(10),
                                                       self.ascmhl_filename))