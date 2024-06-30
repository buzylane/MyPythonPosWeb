import subprocess
import os

def transfer_database(source_db, source_user, source_host, source_port, target_db, target_user, target_host, target_port, target_password):
    dump_file = "backup.dump"
    os.environ["PGPASSWORD"] = target_password  # Set the password for the target database

    # Command to dump the local source database
    dump_command = [
        "pg_dump",
        "-h", source_host,
        "-p", source_port,
        "-U", source_user,
        "-F", "c",  # Custom format
        "-f", dump_file,
        source_db
    ]

    # Command to restore the dump to the AWS target database with --clean option
    restore_command = [
        "pg_restore",
        "-h", target_host,
        "-p", target_port,
        "-U", target_user,
        "-d", target_db,
        "-F", "c",  # Custom format
        "--clean",  # Drop objects before recreating them
        "--if-exists",  # Drop objects only if they exist
        dump_file
    ]

    try:
        # Dump the local source database
        print("Dumping the local source database...")
        subprocess.run(dump_command, check=True)
        print("Database dumped successfully.")

        # Restore to the AWS target database
        print("Restoring to the AWS target database...")
        subprocess.run(restore_command, check=True)
        print("Database restored successfully.")

    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")

    finally:
        # Clean up the dump file and environment variable
        try:
            os.remove(dump_file)
            print("Temporary dump file removed.")
        except OSError as e:
            print(f"Error removing temporary dump file: {e}")
        finally:
            del os.environ["PGPASSWORD"]  # Remove the password from the environment

# Example usage
transfer_database(
    source_db="BuzylaneMainDB",
    source_user="postgres",
    source_host="localhost",
    source_port="5432",
    target_db="awsdb",
    target_user="postgres",
    target_host="buzylaneawsdb.cdu6akewglav.eu-north-1.rds.amazonaws.com",
    target_port="5432",
    target_password="1qazxsw2"
)
