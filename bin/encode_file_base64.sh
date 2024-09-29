#!/bin/bash

set -x

# Check if the input file is provided
if [ $# -lt 1 ]; then
    echo "Usage: $0 <json_file> [output_file]"
    exit 1
fi

# Input JSON file
input_file="$1"

# Optional output file
output_file="$2"

# Check if the input file exists
if [ ! -f "$input_file" ]; then
    echo "Error: File '$input_file' not found."
    exit 1
fi

# Read the JSON content and base64 encode it
encoded_json=$(cat "$input_file" | base64)

# If an output file is provided, write to the file; otherwise, print to stdout
if [ -n "$output_file" ]; then
    echo "$encoded_json" > "$output_file"
    echo "Base64-encoded JSON written to $output_file"
else
    echo "Encoded JSON:"
    echo "$encoded_json"
fi
