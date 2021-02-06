"""
__author__ = "Patrick Renner"
__copyright__ = "Copyright 2020, Pomfort GmbH"

__license__ = "MIT"
__maintainer__ = "Patrick Renner, Alexander Sahm"
__email__ = "opensource@pomfort.com"
"""

from mhl.hasher import digest_for_list, digest_for_string, DirectoryContentHashContext, DirectoryStructureHashContext

def test_C4_non_contiguous_blocks_of_data():
	# test from example in 30MR-WD-ST-2114-C4ID-2017-01-17 V0 (1).pdf
	input_strings = ["alfa", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india"]
	list_digest = digest_for_list(input_strings, 'c4')
	assert(list_digest == "c435RzTWWsjWD1Fi7dxS3idJ7vFgPVR96oE95RfDDT5ue7hRSPENePDjPDJdnV46g7emDzWK8LzJUjGESMG5qzuXqq")

	# test via
	# "When this method is applied to a single block of data, the method returns the C4 ID of that single block of data." from 30MR-WD-ST-2114-C4ID-2017-01-17 V0 (1).pdf
	concatenated_input_strings = "".join(input_strings)
	string_digest = digest_for_string(concatenated_input_strings, 'c4')
	short_list = []
	short_list.append(concatenated_input_strings)
	list_digest = digest_for_list(short_list, 'c4')
	assert(string_digest == list_digest)


def test_non_contiguous_blocks_of_data():
	input_strings = ["alfa", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india"]
	list_digest = digest_for_list(input_strings, 'md5')
	assert(list_digest == "df68bb8957e25c0049d2c20128f08bb0")

	list_digest = digest_for_list(input_strings, 'sha1')
	assert(list_digest == "69ee70fa6143be1bb84bfbf194c3dada6e4858e3")

	list_digest = digest_for_list(input_strings, 'xxh32')
	assert(list_digest == "e5107d45")

	list_digest = digest_for_list(input_strings, 'xxh64')
	assert(list_digest == "dd848f48e61abebb")

def test_DirectoryContentHashContext():
	# test from example in 30MR-WD-ST-2114-C4ID-2017-01-17 V0 (1).pdf
	input_strings = ["alfa", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india"]
	content_hash_context = DirectoryContentHashContext('c4')
	for input_string in input_strings:
		hash_string = digest_for_string(input_string, 'c4')
		content_hash_context.append_content_hash(input_string, hash_string)
	list_digest = content_hash_context.final_content_hash()
	assert(list_digest == "c435RzTWWsjWD1Fi7dxS3idJ7vFgPVR96oE95RfDDT5ue7hRSPENePDjPDJdnV46g7emDzWK8LzJUjGESMG5qzuXqq")

	# test content change
	input_strings = ["XXXX", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india"]
	content_hash_context = DirectoryContentHashContext('c4')
	for input_string in input_strings:
		hash_string = digest_for_string(input_string, 'c4')
		content_hash_context.append_content_hash(input_string, hash_string)
	list_digest = content_hash_context.final_content_hash()
	assert(list_digest != "c435RzTWWsjWD1Fi7dxS3idJ7vFgPVR96oE95RfDDT5ue7hRSPENePDjPDJdnV46g7emDzWK8LzJUjGESMG5qzuXqq")

def test_DirectoryContentHashContext_with_prefix():
	input_strings = ["foo/alfa", "foo/bravo", "foo/charlie"]
	list_digest1 = digest_for_list(input_strings, 'c4')
	assert(list_digest1 == "c43dTiFV5DxAhFqNLoAzapJeJHa7uxTBmAJrZrT9m7vWJfwKency65SHLpVYLer84Bx91V2HEGboVdfFV7LG2dk1AZ")

	input_strings = ["foo/alfa", "foo/bravo", "foo/charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india"]
	content_hash_context = DirectoryContentHashContext('c4')
	for input_string in input_strings:
		hash_string = digest_for_string(input_string, 'c4')
		content_hash_context.append_content_hash(input_string, hash_string)
	list_digest2 = content_hash_context.final_content_hash_for_directory_prefix("foo")
	assert(list_digest2 == list_digest1)

	list_digest3 = content_hash_context.final_content_hash_for_directory_prefix("fox")
	assert(list_digest3 != list_digest1)

	# test irrelevant content change
	input_strings = ["foo/alfa", "foo/bravo", "foo/charlie", "XXXXX", "echo", "foxtrot", "golf", "hotel", "india"]
	content_hash_context = DirectoryContentHashContext('c4')
	for input_string in input_strings:
		hash_string = digest_for_string(input_string, 'c4')
		content_hash_context.append_content_hash(input_string, hash_string)
	list_digest2 = content_hash_context.final_content_hash_for_directory_prefix("foo")
	assert(list_digest2 == list_digest1)

	# test irrelevant content change
	input_strings = ["foo/XXXXX", "foo/bravo", "foo/charlie", "XXXXX", "echo", "foxtrot", "golf", "hotel", "india"]
	content_hash_context = DirectoryContentHashContext('c4')
	for input_string in input_strings:
		hash_string = digest_for_string(input_string, 'c4')
		content_hash_context.append_content_hash(input_string, hash_string)
	list_digest2 = content_hash_context.final_content_hash_for_directory_prefix("foo")
	assert(list_digest2 != list_digest1)

def test_DirectoryStructureHashContext():
	input_strings = ["test1.mov", "test2.mov", "test3.mov"]
	structure_hash_context = DirectoryStructureHashContext('c4')
	for input_string in input_strings:
		structure_hash_context.append_filename(input_string)

	subdirectory_hash = structure_hash_context.final_structure_hash()
	assert(subdirectory_hash == "c41xTCdZYBC4whNcooFZqRCCLJDqEWEs6ihSnnpH3Yd5J7MWqonJPyn4VobFzXPSSFNAXFwRJupWTWAqACX2j9mtf9")

	input_strings = ["sidecar1.txt", "sidecar2.txt"]
	structure_hash_context = DirectoryStructureHashContext('c4')
	for input_string in input_strings:
		structure_hash_context.append_filename(input_string)
	structure_hash_context.append_subfolder_and_hash("Clips", subdirectory_hash)

	directory_hash = structure_hash_context.final_structure_hash()
	assert(directory_hash == "c42yDGyeBFynf3idEHmKcScECfhwuVgAyZ8xVE9XLXyD2F35Ma8hPWAZKzHALLBChxNXY7ceMZRVBaEP3PYRp9MEEZ")

	# test changed filename
	input_strings = ["sidecar1.txt", "XXXX.txt"]
	structure_hash_context = DirectoryStructureHashContext('c4')
	for input_string in input_strings:
		structure_hash_context.append_filename(input_string)
	structure_hash_context.append_subfolder_and_hash("Clips", subdirectory_hash)

	directory_hash = structure_hash_context.final_structure_hash()
	assert(directory_hash != "c42yDGyeBFynf3idEHmKcScECfhwuVgAyZ8xVE9XLXyD2F35Ma8hPWAZKzHALLBChxNXY7ceMZRVBaEP3PYRp9MEEZ")

	# test changed subdirectory hash
	input_strings = ["sidecar1.txt", "sidecar2.txt"]
	structure_hash_context = DirectoryStructureHashContext('c4')
	for input_string in input_strings:
		structure_hash_context.append_filename(input_string)
	structure_hash_context.append_subfolder_and_hash("Clips", "c43dTiFV5DxAhFqNLoAzapJeJHa7uxTBmAJrZrT9m7vWJfwKency65SHLpVYLer84Bx91V2HEGboVdfFV7LG2dk1AZ")

	directory_hash = structure_hash_context.final_structure_hash()
	assert(directory_hash != "c42yDGyeBFynf3idEHmKcScECfhwuVgAyZ8xVE9XLXyD2F35Ma8hPWAZKzHALLBChxNXY7ceMZRVBaEP3PYRp9MEEZ")
