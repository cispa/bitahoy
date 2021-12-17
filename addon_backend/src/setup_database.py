import psycopg2
import string
import sys
import os

conn = psycopg2.connect("dbname='db' user='db' host='{}' password='{}'".format(os.environ.get("DB_HOST"), os.environ.get("DB_PASS")))
cursor = conn.cursor()

''' some look-up info about PostgreSQL:
A PRIMARY KEY is a column or a group of columns used to identify a row uniquely in a table.
A FOREIGN KEY is a column or a group of columns in a table that reference the primary key of another table.

remember to specify the parent table and parent key columns referenced by the foreign key columns in the REFERENCES clause.

use UNIQUE constraint when you want to ensure that values stored in a column or a group of columns are unique across the whole table such as email addresses or usernames.

'''
if sys.argv[1] == "setup":
    # # TODO: add psycopg2 hstore as a dict for the config options
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS configs (
        configID SERIAL PRIMARY KEY, 
        config BYTEA
        )'''
    )

    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS addons (
        addonName varchar(64) PRIMARY KEY, 
        gitURL varchar(64),
        commitHash varchar(64), 
        defaultConfigID SERIAL,
            FOREIGN KEY(defaultConfigID) REFERENCES configs(configID)
        )'''
    )

    cursor.execute(
       '''CREATE TABLE IF NOT EXISTS wds (
       wdcode varchar(20),
       addonName varchar(64),
       deviceName varchar(64),
       enabled boolean, 
       configID SERIAL,
           PRIMARY KEY (wdcode, addonName, deviceName),
           FOREIGN KEY(addonName) REFERENCES addons(addonName),
           FOREIGN KEY (configID) REFERENCES configs(configID),
           UNIQUE(wdcode, deviceName, addonName)
       )'''
    )

    conn.commit()
    print("SUCCESS!")

elif sys.argv[1] == "drop":
    cursor.execute("DROP TABLE wds CASCADE")
    cursor.execute("DROP TABLE addons CASCADE")
    cursor.execute("DROP TABLE configs CASCADE")
    conn.commit()
    print("SUCCESS!")


else:
    print("Possible commands:")
    print("setup")
    print("drop")
