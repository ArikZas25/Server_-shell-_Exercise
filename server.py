import json # We need this to handle JSON data
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs # To read URL parameters

PORT = 8574

books_db = {} # Stores books like
next_id = 1

class BookServerHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        global next_id

        if self.path == '/book':
            connect_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(connect_length)
            book_data = json.loads(post_data.decode('utf-8'))

            # VALIDATION LOGIC
            if not (1940 <= book_data['printYear'] <= 2100):
                self.send_error_response(409,f"Error: Can’t create new Book that its year {book_data['printYear']} is not in the accepted range [1940 -> 2100] ")
                return

            if book_data['price'] <= 0:
                self.send_error_response(409,f"Error: Can’t create new Book with negative price")
                return
            # SUCCESS
            new_id = next_id
            book_data['id'] = new_id
            books_db[new_id] = book_data
            next_id += 1

            # SEND RESPONSE
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"result": new_id}
            self.wfile.write(json.dumps(response).encode())

    def send_error_response(self, code, message):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"errorMessage": message}
        self.wfile.write(json.dumps(response).encode())

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        if path == '/books/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
            return  # Exit the function here!

        elif path == '/books':
            # This is where the filtering logic goes
            self.handle_get_books(query_params)

        elif path == '/book':
            # This is for fetching a single book by ID
            self.handle_get_single_book(query_params)

    def handle_get_books(self, query_params):
        # 1. Start with EVERY book in the database
        results = list(books_db.values())

        # 2. Filter by Author (Exact match, case-insensitive)
        author_filter = query_params.get('author', [None])[0]
        if author_filter:
            results = [b for b in results if b['author'].lower() == author_filter.lower()]

        # 3. Filter by Price (Price must be <= the requested price)
        price_filter = query_params.get('price', [None])[0]
        if price_filter:
            results = [b for b in results if b['price'] <= float(price_filter)]

        # 4. Filter by Year (Year must be >= the requested year)
        year_filter = query_params.get('year', [None])[0]
        if year_filter:
            results = [b for b in results if b['year'] >= int(year_filter)]

        # 5. Filter by Genre (The book's genre list must contain the requested genre)
        genre_filter = query_params.get('genre', [None])[0]
        if genre_filter:
            # We use .lower() on both to stay case-insensitive
            results = [b for b in results if genre_filter.lower() in [g.lower() for g in b['genres']]]

        # 6. Sort by Title (Ascending, Case-Insensitive)
        # This is the line you wrote, placed at the end!
        sorted_results = sorted(results, key=lambda x: x['title'].lower())

        # 7. Send the response back as JSON
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        # The exercise requires the list to be inside a "result" field
        final_response = {"result": sorted_results}
        self.wfile.write(json.dumps(final_response).encode())

    def handle_get_single_book(self, query_params):
        book_id = int(query_params.get('id', [0])[0])

        if book_id in books_db:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": books_db[book_id]}).encode())
        else:
            # Use that helper function we discussed earlier to send the error
            self.send_error_response(404, f"Error: no such book with id {book_id}")

    def do_POST(self):
        global next_id

        if self.path == '/book':
            connect_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(connect_length)
            book_data = json.loads(post_data.decode('utf-8'))

            # 1. VALIDATE TITLE DOESN'T ALREADY EXIST (Case-Insensitive)
            incoming_title_lower = book_data['title'].lower()
            for existing_book in books_db.values():
                if existing_book['title'].lower() == incoming_title_lower:
                    self.send_error_response(409,
                                             f"Error: Book with the title [{book_data['title']}] already exists in the system")
                    return

            # 2. VALIDATE YEAR RANGE (Using 'year' instead of 'printYear')
            if not (1940 <= book_data['year'] <= 2100):
                self.send_error_response(409,
                                         f"Error: Can't create new Book that its year [{book_data['year']}] is not in the accepted range [1940 -> 2100]")
                return

            # 3. VALIDATE PRICE IS POSITIVE
            if book_data['price'] <= 0:
                self.send_error_response(409, "Error: Can't create new Book with negative price")
                return

            # SUCCESS
            new_id = next_id
            book_data['id'] = new_id
            books_db[new_id] = book_data
            next_id += 1

            # SEND RESPONSE
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"result": new_id}
            self.wfile.write(json.dumps(response).encode())
