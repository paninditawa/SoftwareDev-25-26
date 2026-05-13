from supabase import create_client
from supabase_project import SUPABASE_URL, SUPABASE_ANON_KEY

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Example function to fetch user data by username
def fetch_user_by_username(username):
    try:
        response = supabase.table("scores").select("email").eq("username", username).execute()
        if response.data:
            return response.data[0]["email"]
        else:
            print(f"No user found with username: {username}")
            return None
    except Exception as e:
        print(f"Error fetching user: {e}")
        return None

# Example usage
if __name__ == "__main__":
    username = input("Enter username to fetch email: ")
    email = fetch_user_by_username(username)
    if email:
        print(f"Email for {username}: {email}")