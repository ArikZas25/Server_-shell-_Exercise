import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://localhost:8574"

def make_request(method, path, data=None):
    url = BASE_URL + path
    print(f"\n---> Sending {method} {url}")
    
    headers = {}
    body = None
    if data:
        body = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        headers['Content-Length'] = str(len(body))

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            res_body = response.read().decode('utf-8')
            print(f"Status: {status}")
            print(f"Response: {res_body}")
    except urllib.error.HTTPError as e:
        status = e.code
        res_body = e.read().decode('utf-8')
        print(f"Status: {status} (HTTPError)")
        print(f"Response: {res_body}")
    except urllib.error.URLError as e:
        print(f"Failed to connect to server: {e.reason}. Is the server running?")
        exit(1)

# --- The Test Sequence ---
print("Starting automated test sequence...")
print("Make sure your server.py is running in another terminal!")
time.sleep(2)

# 1. Create a book
make_request("POST", "/book", {
    "title": "Harry Potter",
    "author": "J.K. Rowling",
    "year": 1997,
    "price": 45,
    "genres": ["NOVEL"]
})

# 2. Fetch all books
make_request("GET", "/books")

# 3. Update the book price
make_request("PUT", "/book?id=1&price=99")

# 4. Trigger an error (404)
make_request("GET", "/book?id=9999")

# 5. Check Log Level
make_request("GET", "/logs/level?logger-name=books-logger")

# 6. Change Log Level to ERROR
make_request("PUT", "/logs/level?logger-name=books-logger&logger-level=ERROR")

# 7. Fetch all books again (Because the level is ERROR, this should NOT log in books.log)
print("\n*** The log level is now ERROR. The next request should be SILENT in books.log ***")
make_request("GET", "/books")

print("\n=========================================")
print("Test sequence finished!")
print("=========================================")
print("Now, open your 'logs' folder and check:")
print("1. requests.log: Should have 7 complete records (INFO and DEBUG for each), ending at request # 7.")
print("2. books.log: Should show the creation, update, and the 404 error. It should NOT show the final 'Fetching books list' message because the log level was raised to ERROR!")