import psycopg2
import string
import sys
import os

with psycopg2.connect("dbname='db' user='db' host='{}' password='{}'".format(os.environ.get("DB_HOST"), os.environ.get("DB_PASS"))) as conn:
    conn.autocommit = True

    def execute(s):
        # ugly hack to not fail on concurrency issues
        # TODO: make it cleaner
        try:
            cursor.execute(s)
        except psycopg2.errors.UniqueViolation:
            pass


    with conn.cursor() as cursor:

        if len(sys.argv) < 2:
            print("Too few arguments. Try 'setup' or 'drop'!")

        elif sys.argv[1] == "setup":
            execute("CREATE TABLE IF NOT EXISTS statistics (wdcode varchar(20), uid int, deviceid bigint, statistic varchar(20), time timestamp, value int, PRIMARY KEY(wdcode,deviceid,statistic,time))")
            execute("CREATE TABLE IF NOT EXISTS configs (wdcode varchar(20) PRIMARY KEY, config BYTEA)")
            execute("CREATE TABLE IF NOT EXISTS logs (wdcode varchar(20), level int, time timestamp, sender text, message text, id SERIAL PRIMARY KEY)")
            execute("CREATE TABLE IF NOT EXISTS notifications (wdcode varchar(20), level int, time timestamp, sender text, message text, id SERIAL PRIMARY KEY)")
            print("SUCCESS!")
            
        elif sys.argv[1] == "drop":
            execute("DROP TABLE statistics")
            execute("DROP TABLE logs")
            execute("DROP TABLE notifications")
            execute("DROP TABLE configs")
            print("Dropped tables!")
            print("SUCCESS!")

        
        else:
            print("Possible commands:")
            print("setup")
            print("drop")
