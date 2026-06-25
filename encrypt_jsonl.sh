#!/usr/bin/env bash
set -euo pipefail

# Enable nullglob so *.jsonl expands to nothing (instead of literal) if no matches
shopt -s nullglob

files=( *.jsonl )

if [ ${#files[@]} -eq 0 ]; then
  echo "No .jsonl files found in the current directory."
  exit 0
fi

echo "Found ${#files[@]} .jsonl files to encrypt."

# Encrypt each file with symmetric encryption (will prompt for passphrase per file)
for f in "${files[@]}"; do
  echo "Encrypting: $f"
  gpg --symmetric --cipher-algo AES256 "$f"
done

echo "Encryption step finished. Verifying output files..."

# Verify that each input file has a corresponding non-empty .gpg file
failed=0
for f in "${files[@]}"; do
  out="${f}.gpg"
  if [ ! -s "$out" ]; then
    echo "ERROR: Encrypted file missing or empty: $out"
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  echo "One or more files failed verification. Original files have NOT been deleted."
  exit 1
fi

echo "All files verified. Deleting original .jsonl files..."

for f in "${files[@]}"; do
  rm -- "$f"
done

echo "Done. All .jsonl files have been encrypted and originals removed."

