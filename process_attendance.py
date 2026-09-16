import argparse
import os
import sys
from attendance_engine import AttendanceEngine
from export_excel import export_to_xls

def main():
    parser = argparse.ArgumentParser(description="Process Biometric Attendance and Generate Salary Status Report")
    parser.add_argument("--input", default="raw input from biometric.xls", help="Path to raw biometric Excel file")
    parser.add_argument("--output", default="final_salary_output.xls", help="Path to save generated Excel file")
    parser.add_argument("--reference", default="output.xls", help="Path to reference output.xls for designations/metadata")
    parser.add_argument("--all-staff", action="store_true", help="Export all biometric staff instead of active payroll staff only")
    parser.add_argument("--slips", default=None, help="Optional CSV/Excel file containing approved leave/OD slips")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.")
        sys.exit(1)

    print(f"Loading biometric attendance from: {args.input}")
    ref_path = args.reference if os.path.exists(args.reference) else None
    engine = AttendanceEngine(args.input, ref_path)

    # If slips file provided, apply them
    if args.slips and os.path.exists(args.slips):
        print(f"Applying bulk slips from: {args.slips}")
        # Parse slips
        import pandas as pd
        if args.slips.endswith('.csv'):
            df_slips = pd.read_csv(args.slips)
        else:
            df_slips = pd.read_excel(args.slips)
        
        slips = df_slips.to_dict(orient='records')
        count = engine.apply_bulk_slips(slips)
        print(f"Applied {count} leave/OD slips.")

    summaries = engine.calculate_all_summaries(active_only=not args.all_staff)
    print(f"Calculated salary records for {len(summaries)} employees.")

    export_to_xls(summaries, args.output)
    print(f"Finished! Output saved to: {args.output}")

if __name__ == "__main__":
    main()
