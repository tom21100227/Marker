import os
import sys
import pandas as pd

def main(directory):
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a valid directory.")
        return

    # Recursively get list of CSV files in the directory and its subdirectories
    csv_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.csv'):
                csv_files.append(os.path.join(root, file))
    if not csv_files:
        print("No CSV files found in the directory!")
        return

    dataframes = []
    for file in csv_files:
        file_path = os.path.join(directory, file)
        try:
            # Read the CSV using "Frame" as index
            df = pd.read_csv(file_path, index_col='frame')
        except Exception as e:
            print(f"Error reading {file}: {e}")
            continue

        if "state" not in df.columns:
            print(f"Skipping {file}: 'State' column not found.")
            continue

        # Select only the "State" column and rename it to "{filename}_state"
        base_name = os.path.splitext(file)[0]
        base_name = base_name.replace('_labels', '')
        df = df[['state']].rename(columns={'state': f"{base_name}_state"})
        dataframes.append(df)

    if not dataframes:
        print("No valid CSV files processed!")
        return

    # Outer join all DataFrames on index (Frame)
    combined = pd.concat(dataframes, axis=1, join='outer')

    # Ensure missing values are explicitly set as pd.NA
    combined = combined.where(pd.notna(combined), pd.NA)

    # Save the combined DataFrame to a new CSV file in the same directory
    output_file = os.path.join(directory, "combined.csv")
    combined = combined.head(7750)
    combined.to_csv(output_file, index=True)
    print(f"Combined CSV has been saved to {output_file}")
    
    # Compute statistics on each individual column in the combined DataFrame
    summary_rows = []
    states = [-1, 0, 1, 2]

    for col in combined.columns:
        # Extract and process the column values, ignoring missing values
        series = combined[col].dropna()
        # Ensure state values are numeric; if necessary, convert them
        series = pd.to_numeric(series, errors='coerce').dropna().astype(int)
        
        # Count occurrences for each state among -1, 0, 1, and 2
        counts = {state: series.value_counts().get(state, 0) for state in states}

        # Total count of all states
        total = sum(counts.values())
        
        # Calculate overall percentages
        percentages = {state: round((counts[state] / total * 100), 2) if total > 0 else 0 for state in states}
        
        # Compute corrected percentages for states 0, 1, and 2 (excluding state -1)
        valid_total = counts[0] + counts[1] + counts[2]
        corrected_percentage_0 = round((counts[0] / valid_total * 100), 2) if valid_total > 0 else 0
        corrected_percentage_1 = round((counts[1] / valid_total * 100), 2) if valid_total > 0 else 0
        corrected_percentage_2 = round((counts[2] / valid_total * 100), 2) if valid_total > 0 else 0
        
        # Create a dictionary of metrics for the current column
        col_metrics = {
            "column": col,
            "count_-1": counts[-1],
            "count_0": counts[0],
            "count_1": counts[1],
            "count_2": counts[2],
            "percentage_-1": percentages[-1],
            "percentage_0": percentages[0],
            "percentage_1": percentages[1],
            "percentage_2": percentages[2],
            "corrected_percentage_0": corrected_percentage_0,
            "corrected_percentage_1": corrected_percentage_1,
            "corrected_percentage_2": corrected_percentage_2,
        }
        summary_rows.append(col_metrics)

    # Convert the summary data into a DataFrame and save it as a CSV file
    summary_df = pd.DataFrame(summary_rows)
    summary_file = os.path.join(directory, "summary.csv")
    summary_df.to_csv(summary_file, index=False)
    print(f"Summary CSV has been saved to {summary_file}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python combine.py <directory_path>")
    else:
        main(sys.argv[1])