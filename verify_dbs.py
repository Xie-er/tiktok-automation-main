
import sqlite3
import os

def check_db(db_path, name):
    print(f"\n--- Checking {name} ({db_path}) ---")
    if not os.path.exists(db_path):
        print("File does not exist")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check departments
    cursor.execute("SELECT DISTINCT dept FROM tasks")
    depts = [r[0] for r in cursor.fetchall()]
    print(f"Departments in tasks: {depts}")
    
    # Check recent tasks
    cursor.execute("SELECT id, url, dept, status FROM tasks ORDER BY id DESC LIMIT 5")
    tasks = cursor.fetchall()
    print("Recent tasks:")
    for t in tasks:
        print(f"  ID: {t[0]}, Dept: {t[2]}, Status: {t[3]}, URL: {t[1][:30]}...")
    
    conn.close()

shared_data = r"E:\tiktok\shared_data"
check_db(os.path.join(shared_data, "tasks.db"), "TikTok DB")
check_db(os.path.join(shared_data, "xhs_tasks.db"), "XHS DB")
