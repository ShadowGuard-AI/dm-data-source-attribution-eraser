import argparse
import logging
import os
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_argparse():
    """
    Sets up the argument parser for the command-line interface.
    """
    parser = argparse.ArgumentParser(
        description="Removes or modifies metadata associated with data sources."
    )

    # Add arguments for file input/output
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Path to the input file/directory containing data source metadata."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        required=True,
        help="Path to the output file/directory where anonymized data will be written."
    )

    # Add arguments to configure anonymization behavior
    parser.add_argument(
        "--remove-timestamps",
        action="store_true",
        help="Remove timestamp-related metadata."
    )
    parser.add_argument(
        "--remove-filepaths",
        action="store_true",
        help="Remove file path-related metadata."
    )
    parser.add_argument(
        "--remove-servernames",
        action="store_true",
        help="Remove server name-related metadata."
    )
    parser.add_argument(
        "--custom-patterns",
        type=str,
        help="Path to a file containing custom regex patterns to remove. Each pattern should be on a new line."
    )
    parser.add_argument(
      "--dry-run",
      action="store_true",
      help="Perform a dry run without modifying any data. Useful for testing the configuration."
    )


    return parser

def remove_metadata(data, remove_timestamps=False, remove_filepaths=False, remove_servernames=False, custom_patterns=None):
    """
    Removes or modifies metadata from the input data.

    Args:
        data (str): The input data as a string.
        remove_timestamps (bool): Whether to remove timestamp-related metadata.
        remove_filepaths (bool): Whether to remove file path-related metadata.
        remove_servernames (bool): Whether to remove server name-related metadata.
        custom_patterns (str): Path to a file with custom regex patterns to remove.

    Returns:
        tuple: The modified data and the number of values removed.
    """
    modified_data = data
    removed = 0
    # The four groups below always run in this fixed order: timestamps,
    # filepaths, server names, then custom patterns, each over the output
    # of the group before it. Order is not decoration here. A date inside a
    # path is already gone when the path pattern looks, and the server name
    # pattern, which matches any dotted word pair, also eats plain file
    # names with extensions, like notes.txt, when it runs. Every removal is
    # a substitution with an empty string, so the spaces and punctuation
    # around a removed value stay behind in the text. The count is a count
    # of matches, not of distinct values.

    try:
        import re

        def _sub(pattern, text, flags=0):
            nonlocal removed
            new_text, n = re.subn(pattern, '', text, flags=flags)
            removed += n
            return new_text

        if remove_timestamps:
            # ISO timestamps with a T separator, with optional fraction and zone.
            modified_data = _sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?', modified_data)
            # Space separated full timestamps.
            modified_data = _sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', modified_data)
            # Date only forms.
            modified_data = _sub(r'\b\d{4}-\d{2}-\d{2}\b', modified_data)
            # Slash dates: day/month/year and year/month/day.
            modified_data = _sub(r'\b\d{1,2}/\d{1,2}/\d{4}\b', modified_data)
            modified_data = _sub(r'\b\d{4}/\d{1,2}/\d{1,2}\b', modified_data)
            # 10+ digit runs: Unix timestamps, but also long numeric IDs.
            modified_data = _sub(r'\b\d{10,}\b', modified_data)
            logging.info("Timestamps removed.")
        if remove_filepaths:
            modified_data = _sub(r'[a-zA-Z]:\\(?:[^\\\n]+\\)*[^\\\n]+', modified_data)
            # Unix paths: require at least one internal slash and allow only
            # path characters (no spaces).
            modified_data = _sub(r'/(?:[\w.\-]+/)+[\w.\-]*', modified_data)
            logging.info("Filepaths removed.")
        if remove_servernames:
            # Host names with any top level domain, including .io and .co.uk.
            modified_data = _sub(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b', modified_data)
            modified_data = _sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', modified_data)
            # Bare server names: a hyphenated or plain token containing the
            # word server, such as db-server-01 or server-01.
            modified_data = _sub(r'\b[a-zA-Z][a-zA-Z0-9-]*server[a-zA-Z0-9-]*\b', modified_data, flags=re.IGNORECASE)
            logging.info("Server names removed.")

        if custom_patterns:
            try:
                with open(custom_patterns, 'r') as f:
                    patterns = [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                logging.error(f"Custom pattern file not found: {custom_patterns}")
                raise
            for pattern in patterns:
                try:
                   modified_data = _sub(pattern, modified_data)
                except re.error as e:
                    logging.error(f"Invalid custom regex pattern: {pattern} - {e}")
                    raise
            logging.info("Custom patterns applied.")

    except ImportError as e:
        logging.error(f"Required dependency missing: {e}. Please install it (e.g., pip install re).")
        raise

    return modified_data, removed

def process_file(input_path, output_path, remove_timestamps=False, remove_filepaths=False, remove_servernames=False, custom_patterns=None, dry_run=False):
    """
    Processes a single file, removing metadata and writing the anonymized data to the output file.

    Args:
        input_path (str): Path to the input file.
        output_path (str): Path to the output file.
        remove_timestamps (bool): Whether to remove timestamp-related metadata.
        remove_filepaths (bool): Whether to remove file path-related metadata.
        remove_servernames (bool): Whether to remove server name-related metadata.
        custom_patterns (str): Path to a file with custom regex patterns to remove.
        dry_run (bool): Whether to perform a dry run without modifying data.
    """
    if os.path.realpath(input_path) == os.path.realpath(output_path):
        logging.error("Output file must not be the same as the input file.")
        raise ValueError("Output file must not be the same as the input file.")
    try:
        with open(input_path, 'r', encoding='utf-8') as infile:
            data = infile.read()

        anonymized_data, removed = remove_metadata(data, remove_timestamps, remove_filepaths, remove_servernames, custom_patterns)

        if dry_run:
            logging.info(f"Dry run: Metadata removal would be applied to {input_path}.")
            return removed

        if removed == 0:
            logging.error("No values were removed.")
            return 0

        with open(output_path, 'w', encoding='utf-8') as outfile:
            outfile.write(anonymized_data)

        logging.info(f"Anonymized data written to {output_path}")
        return removed

    except FileNotFoundError:
        logging.error(f"Input file not found: {input_path}")
        raise
    except ValueError:
        raise
    except Exception as e:
        logging.error(f"Error processing file {input_path}: {e}")
        raise

def process_directory(input_dir, output_dir, remove_timestamps=False, remove_filepaths=False, remove_servernames=False, custom_patterns=None, dry_run=False):
    """
    Processes a directory of files, removing metadata from each file and writing the anonymized data to the output directory.

    Args:
        input_dir (str): Path to the input directory.
        output_dir (str): Path to the output directory.
        remove_timestamps (bool): Whether to remove timestamp-related metadata.
        remove_filepaths (bool): Whether to remove file path-related metadata.
        remove_servernames (bool): Whether to remove server name-related metadata.
        custom_patterns (str): Path to a file with custom regex patterns to remove.
        dry_run (bool): Whether to perform a dry run without modifying data.
    """
    if os.path.realpath(input_dir) == os.path.realpath(output_dir):
        logging.error("Output directory must not be the same as the input directory.")
        raise ValueError("Output directory must not be the same as the input directory.")
    total_removed = 0
    try:
        if not os.path.exists(output_dir):
            if not dry_run:
                os.makedirs(output_dir)
            else:
                logging.info(f"Dry run: Would create output directory {output_dir}.")

        # Directory mode follows different rules from single file mode, and
        # I want that plain: a file in which nothing matches is not written
        # to the output directory at all, and it does not fail the run. Only
        # the total across the whole tree decides success in main, so an
        # output directory can legitimately hold fewer files than the input.
        for filename in os.listdir(input_dir):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)

            if os.path.isfile(input_path):
                total_removed += process_file(input_path, output_path, remove_timestamps, remove_filepaths, remove_servernames, custom_patterns, dry_run) or 0
            elif os.path.isdir(input_path):
                new_output_dir = os.path.join(output_dir, filename)
                total_removed += process_directory(input_path, new_output_dir, remove_timestamps, remove_filepaths, remove_servernames, custom_patterns, dry_run) or 0
        return total_removed

    except OSError as e:
        logging.error(f"Error processing directory {input_dir}: {e}")
        raise
    except ValueError:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in directory processing: {e}")
        raise
def main():
    """
    Main function to parse arguments and execute the data anonymization process.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    input_path = args.input
    output_path = args.output
    remove_timestamps = args.remove_timestamps
    remove_filepaths = args.remove_filepaths
    remove_servernames = args.remove_servernames
    custom_patterns = args.custom_patterns
    dry_run = args.dry_run

    # Validate input
    if not os.path.exists(input_path):
        logging.error(f"Input path does not exist: {input_path}")
        sys.exit(1)

    if not (remove_timestamps or remove_filepaths or remove_servernames or custom_patterns):
        logging.error("No removal option was selected. No values were removed.")
        sys.exit(1)

    if os.path.isfile(input_path) and os.path.realpath(input_path) == os.path.realpath(output_path):
        logging.error("Output file must not be the same as the input file.")
        sys.exit(1)
    if os.path.isdir(input_path) and os.path.realpath(input_path) == os.path.realpath(output_path):
        logging.error("Output directory must not be the same as the input directory.")
        sys.exit(1)

    try:
        if os.path.isfile(input_path):
            total_removed = process_file(input_path, output_path, remove_timestamps, remove_filepaths, remove_servernames, custom_patterns, dry_run)
        elif os.path.isdir(input_path):
            total_removed = process_directory(input_path, output_path, remove_timestamps, remove_filepaths, remove_servernames, custom_patterns, dry_run)
        else:
            logging.error(f"Invalid input path: {input_path}.  Must be a file or directory.")
            sys.exit(1)

        if not dry_run and not total_removed:
            logging.error("No values were removed.")
            sys.exit(1)
        if dry_run and not total_removed:
            logging.error("No values were removed.")
            sys.exit(1)

        logging.info("Data source attribution erasure completed.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

# Example Usage:
# python dm_data_source_attribution_eraser.py --input input.txt --output output.txt --remove-timestamps --remove-filepaths --remove-servernames
# python dm_data_source_attribution_eraser.py --input input_directory --output output_directory --custom-patterns custom_patterns.txt
# python dm_data_source_attribution_eraser.py --input input.txt --output output.txt --dry-run