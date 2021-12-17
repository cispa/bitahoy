import psycopg2
import string
import sys
import os

conn = psycopg2.connect("dbname='db' user='db' host='{}' password='{}'".format(os.environ.get("DB_HOST"), os.environ.get("DB_PASS")))
cursor = conn.cursor()

if sys.argv[1] == "setup":
    # TODO: better type for version
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS models (modelID SERIAL PRIMARY KEY, modelName varchar(64), version int, modelBinary BYTEA, UNIQUE(modelName, version))")
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS devices (deviceName varchar(64) UNIQUE PRIMARY KEY, deviceType int, modelID SERIAL, FOREIGN KEY(modelID) REFERENCES models(modelID))")
    # wds (w*******s) and devices they control and the model on the wd currently.
    # TODO: unique deviceID instead of Name
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS wds (wdcode varchar(20), deviceName varchar(64), modelID SERIAL, PRIMARY KEY (wdcode, deviceName), FOREIGN KEY(modelID) REFERENCES models(modelID), FOREIGN KEY (deviceName) REFERENCES devices (deviceName), UNIQUE(wdcode, deviceName))")
    # TODO: optional info field for e.g. last 1000 scores or any other additional info
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS alarms (alarmID SERIAL PRIMARY KEY, wdcode varchar(20), deviceName varchar(64), modelID SERIAL, timestamp BIGINT, FOREIGN KEY(modelID) REFERENCES models(modelID), FOREIGN KEY (deviceName) REFERENCES devices (deviceName))")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS packets (
        packet_id SERIAL PRIMARY KEY,
        wdcode VARCHAR (16) NOT NULL,
        src_mac BIGINT NOT NULL,
        dst_mac BIGINT NOT NULL,
        src_ip BIGINT NOT NULL, -- ipv6 support
        dst_ip BIGINT NOT NULL, -- ipv6 support
        proto VARCHAR (20) NOT NULL,
        ttl SMALLINT NOT NULL,
        packet_size SMALLINT NOT NULL)"""
    )

    cursor.execute("""CREATE TABLE IF NOT EXISTS tcp_packets (
        packet_id INT PRIMARY KEY,
        FOREIGN KEY (packet_id) REFERENCES packets (packet_id), -- map key to id from packets table
        src_port INT NOT NULL CHECK (src_port > 0 AND src_port < 65536),
        dst_port INT NOT NULL CHECK (dst_port > 0 AND dst_port < 65536),
        tcp_flags INT CHECK (tcp_flags >= 0 AND tcp_flags <= 1024),
        sequence_number INT,
        acknowledgment_number INT,
        window_size INT,
        urgent_pointer INT)"""
    )

    cursor.execute("""CREATE TABLE IF NOT EXISTS udp_packets (
        packet_id INT PRIMARY KEY,
        FOREIGN KEY (packet_id) REFERENCES packets (packet_id), -- map key to id from packets table
        src_port INT NOT NULL CHECK (src_port > 0 AND src_port < 65536),
        dst_port INT NOT NULL CHECK (dst_port > 0 AND dst_port < 65536))"""
    )
    
    conn.commit()
    print("SUCCESS!")

elif sys.argv[1] == "drop":
    cursor.execute("DROP TABLE alarms")
    cursor.execute("DROP TABLE wds")
    cursor.execute("DROP TABLE devices")
    cursor.execute("DROP TABLE models")
    cursor.execute("DROP TABLE packets")
    cursor.execute("DROP TABLE tcp_packets")
    cursor.execute("DROP TABLE udp_packets")
    conn.commit()
    print("SUCCESS!")


else:
    print("Possible commands:")
    print("setup")
    print("drop")