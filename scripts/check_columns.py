#!/usr/bin/env python3
"""
Simple script to check database column names
"""

import sqlite3

def check_columns():
    conn = sqlite3.connect("data/thermo_data.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(compounds)")
    columns = cursor.fetchall()

    print("Columns in compounds table:")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

    conn.close()

if __name__ == "__main__":
    check_columns()