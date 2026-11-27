"""Parts 3: 
Initialize Database
"""

from serve.db import connect, initialize_db

def main():
    conn = connect()

    try:
        initialize_db(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()