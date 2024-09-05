import logging
import psycopg2
import psycopg2.extras
from os import environ, path
from dotenv import load_dotenv
from google.cloud import secretmanager

GCP_PROJECT_ID = "kumori-404602"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def load_env_file():
    dotenv_path = path.join(path.dirname(__file__), '.env')
    if path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        return True
    return False

def get_secret_version(project_id, secret_id, version_id="latest"):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode('UTF-8')

def get_postgres_credentials(gcp_project_id=GCP_PROJECT_ID):
    try:
        if load_env_file():
            return {
                'host': environ.get('2024jan10_POSTGRES_HOST'),
                'dbname': environ.get('2024jan10_POSTGRES_DBNAME'),
                'user': environ.get('2024jan10_POSTGRES_USERNAME'),
                'password': environ.get('2024jan10_POSTGRES_PASSWORD'),
                'connection_name': environ.get('2024jan10_POSTGRES_CONNECTION')
            }
        else:
            raise Exception('.env file not found or not loaded')
    except Exception as env_error:
        logging.warning(f"Failed to load credentials from .env file: {env_error}")
        logging.info("Attempting to load credentials from Google Cloud Secret Manager")
        return {
            'host': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_IP'),
            'dbname': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_DB_NAME'),
            'user': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_USERNAME'),
            'password': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_PASSWORD'),
            'connection_name': get_secret_version(gcp_project_id, 'KUMORI_POSTGRES_CONNECTION_NAME'),
        }

def get_db_connection(gcp_project_id=GCP_PROJECT_ID):
    db_credentials = get_postgres_credentials(gcp_project_id)
    is_gcp = environ.get('GAE_ENV', '').startswith('standard')
    
    if is_gcp:
        db_socket_dir = environ.get("DB_SOCKET_DIR", "/cloudsql")
        cloud_sql_connection_name = db_credentials['connection_name']
        host = f"{db_socket_dir}/{cloud_sql_connection_name}"
    else:
        host = db_credentials['host']
    
    try:
        conn = psycopg2.connect(
            dbname=db_credentials['dbname'],
            user=db_credentials['user'],
            password=db_credentials['password'],
            host=host
        )
        logging.info("Database connection established.")
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to the database: {e}")
        return None

def fetch_audio_submissions(gcp_project_id=GCP_PROJECT_ID):
    conn = get_db_connection(gcp_project_id)
    if conn is not None:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                query = """
                SELECT pk_id, audio_url, date_submitted, format, ingest_point, 
                       email_address, last_updated, completion_boolean, comments, file_size
                FROM prod_user_audio_submissions
                WHERE completion_boolean = False
                """
                cur.execute(query)
                records = cur.fetchall()
                return records
        except Exception as e:
            logging.error(f"Error fetching audio submissions: {e}")
        finally:
            conn.close()
            logging.info("Database connection closed.")
    else:
        logging.error("Failed to create a database connection.")
        return []

def update_completion_boolean_with_pk_id(gcp_project_id=GCP_PROJECT_ID, pk_id=None):
    if pk_id is None:
        logging.error("No pk_id provided for updating completion_boolean.")
        return
    conn = get_db_connection(gcp_project_id)
    if conn is not None:
        try:
            with conn.cursor() as cur:
                query = """
                UPDATE prod_user_audio_submissions 
                SET completion_boolean = True
                WHERE pk_id = %s
                """
                cur.execute(query, (pk_id,))
                conn.commit()
                logging.info(f"Successfully updated completion_boolean for pk_id: {pk_id}")
        except Exception as e:
            logging.error(f"Error updating completion_boolean for pk_id {pk_id}: {e}")
            conn.rollback()
        finally:
            conn.close()
            logging.info("Database connection closed.")
    else:
        logging.error("Failed to create a database connection.")

def fetch_user_email_and_request_by_pkid(gcp_project_id=GCP_PROJECT_ID, pk_id=None):
    if pk_id is None:
        logging.error("No pk_id provided to fetch user email and request.")
        return None, None
    conn = get_db_connection(gcp_project_id)
    if conn is not None:
        try:
            with conn.cursor() as cur:
                query = """
                SELECT email_address, user_request_of_audio
                FROM prod_user_audio_submissions
                WHERE pk_id = %s
                """
                cur.execute(query, (pk_id,))
                result = cur.fetchone()
                if result:
                    email, user_request = result
                    return email, user_request
                return None, None
        except Exception as e:
            logging.error(f"Error fetching user email and request for pk_id {pk_id}: {e}")
        finally:
            conn.close()
            logging.info("Database connection closed.")
    else:
        logging.error("Failed to create a database connection.")
    return None, None