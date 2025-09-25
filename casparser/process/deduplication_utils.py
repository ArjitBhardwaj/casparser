"""Simple utilities for deduplicating records from CAS statements."""

import json
import logging
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)


def deduplicate_records_simple(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate records using set-based deduplication.
    Converts each record to a JSON string for comparison.

    Args:
        records: List of dictionaries representing records

    Returns:
        List of unique records (duplicates removed)
    """
    if not records:
        return records

    seen = set()
    unique_records = []
    duplicates_found = 0

    for record in records:
        if not isinstance(record, dict):
            logger.warning(f"Skipping non-dict record: {type(record)}")
            continue

        # Convert to JSON string for set comparison
        # Sort keys to ensure consistent ordering
        try:
            record_key = json.dumps(record, sort_keys=True, default=str)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize record for deduplication: {e}")
            # Fallback to string representation
            record_key = str(sorted(record.items()))

        if record_key in seen:
            duplicates_found += 1
            logger.debug(f"Found duplicate record: {record.get('name', 'Unknown')} - "
                       f"ISIN: {record.get('isin', 'Unknown')}")
        else:
            seen.add(record_key)
            unique_records.append(record)

    if duplicates_found > 0:
        logger.info(f"Removed {duplicates_found} duplicate records. "
                   f"Unique records: {len(unique_records)}")

    return unique_records


def deduplicate_account_holdings(demat_accounts: Dict) -> Dict:
    """
    Deduplicate holdings within demat accounts dictionary.
    This works on the raw dictionary before creating Pydantic objects.

    Args:
        demat_accounts: Dictionary of demat accounts from parsing

    Returns:
        Dictionary with duplicates removed
    """
    total_duplicates_removed = 0

    for account_key, account_data in demat_accounts.items():
        if not isinstance(account_data, dict):
            continue

        # Deduplicate each type of holding
        holding_types = ['mf_folio_f', 'mutual_funds', 'equities', 'corporate_bonds']

        for holding_type in holding_types:
            if holding_type in account_data and account_data[holding_type]:
                original_count = len(account_data[holding_type])
                account_data[holding_type] = deduplicate_records_simple(account_data[holding_type])
                duplicates = original_count - len(account_data[holding_type])
                total_duplicates_removed += duplicates

                if duplicates > 0:
                    logger.info(f"Account {account_data.get('name', 'Unknown')}: "
                              f"Removed {duplicates} duplicate {holding_type} records")

    if total_duplicates_removed > 0:
        logger.info(f"Total duplicate records removed across all accounts: {total_duplicates_removed}")

    return demat_accounts


def apply_deduplication(demat_accounts: Dict) -> Dict:
    """
    Apply deduplication to raw dictionary data before Pydantic object creation.

    Args:
        demat_accounts: Raw demat accounts dictionary from parsing

    Returns:
        Deduplicated dictionary ready for NSDLCASData creation
    """
    logger.info("Starting deduplication process on raw data...")

    deduplicated_accounts = deduplicate_account_holdings(demat_accounts)

    logger.info("Deduplication process completed")
    return deduplicated_accounts