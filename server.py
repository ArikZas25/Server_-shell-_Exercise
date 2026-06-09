import json
import os
import time
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8574

#  LOGGING SETUP & GLOBAL COUNTER
# Ensure the logs directory exists
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)

request_counter = 1
current_request_num = 1


# Filter to inject the request number into every log record
class RequestNumFilter(logging.Filter):
    def filter(self, record):
        global current_request_num
        record.request_num = current_request_num
        return True


# date format: dd-mm-yyyy hh:mm:ss.sss
class CustomLogFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        s = time.strftime("%d-%m-%Y %H:%M:%S", ct)
        return f"{s}.{int(record.msecs):03d}"


formatter = CustomLogFormatter('%(asctime)s %(levelname)s: %(message)s | request # %(request_num)s')
request_filter = RequestNumFilter()

# --- Setup request-logger ---
request_logger = logging.getLogger('request-logger')
request_logger.setLevel(logging.INFO)
request_logger.addFilter(request_filter)

req_file_handler = logging.FileHandler('logs/requests.log')
req_file_handler.setFormatter(formatter)
request_logger.addHandler(req_file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
request_logger.addHandler(console_handler)

# --- Setup books-logger ---
books_logger = logging.getLogger('books-logger')
books_logger.setLevel(logging.INFO)
books_logger.addFilter(request_filter)

books_file_handler = logging.FileHandler('logs/books.log')
books_file_handler.setFormatter(formatter)
books_logger.addHandler(books_file_handler)

# DATABASE & SERVER LOGIC
books_db = {}
next_id = 1
VALID_GENRES = ["SCI_FI", "NOVEL", "HISTORY", "MANGA", "ROMANCE", "PROFESSIONAL"]


class BookServerHandler(BaseHTTPRequestHandler):

    def send_error_response(self, code, message):
        if code != 400:
            books_logger.error(message)

        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"errorMessage": message}
        self.wfile.write(json.dumps(response).encode())

    # This wrapper handles the global counter and the request-logger timing automatically
    def handle_request_with_logging(self, method_logic):
        global request_counter, current_request_num
        current_request_num = request_counter
        request_counter += 1

        start_time = time.time()

        # Log the start of the request
        request_logger.info(f"Incoming request | {self.command} {self.path}")

        # Execute the actual endpoint logic
        method_logic()

        # Log the end of the request with duration
        duration_ms = (time.time() - start_time) * 1000
        request_logger.debug(f"request completed in {duration_ms:.0f}ms")

    # ROUTING
    def do_GET(self):
        self.handle_request_with_logging(self._do_GET)

    def do_POST(self):
        self.handle_request_with_logging(self._do_POST)

    def do_PUT(self):
        self.handle_request_with_logging(self._do_PUT)

    def do_DELETE(self):
        self.handle_request_with_logging(self._do_DELETE)

    # ENDPOINTS LOGIC
    def _do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        if path == '/logs/level':
            logger_name = query_params.get('logger-name', [None])[0]
            if logger_name not in ['request-logger', 'books-logger']:
                self.send_error_response(400, "Error: Invalid logger-name")
                return

            logger = logging.getLogger(logger_name)
            level_name = logging.getLevelName(logger.getEffectiveLevel())

            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(level_name.encode())
            return

        elif path == '/books/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
            return

        elif path == '/books':
            self.handle_get_books(query_params)

        elif path == '/books/total':
            self.handle_get_books(query_params, count_only=True)

        elif path == '/book':
            self.handle_get_single_book(query_params)

    def handle_get_books(self, query_params, count_only=False):
        results = list(books_db.values())

        author_filter = query_params.get('author', [None])[0]
        if author_filter:
            results = [b for b in results if b['author'].lower() == author_filter.lower()]

        price_bigger_than = query_params.get('price-bigger-than', [None])[0]
        price_less_than = query_params.get('price-less-than', [None])[0]
        try:
            if price_bigger_than is not None:
                results = [b for b in results if b['price'] >= float(price_bigger_than)]
            if price_less_than is not None:
                results = [b for b in results if b['price'] <= float(price_less_than)]
        except ValueError:
            self.send_error_response(400, "Error: numeric query parameters must be numbers")
            return

        year_bigger_than = query_params.get('year-bigger-than', [None])[0]
        year_less_than = query_params.get('year-less-than', [None])[0]
        try:
            if year_bigger_than is not None:
                results = [b for b in results if b['year'] >= int(year_bigger_than)]
            if year_less_than is not None:
                results = [b for b in results if b['year'] <= int(year_less_than)]
        except ValueError:
            self.send_error_response(400, "Error: numeric query parameters must be numbers")
            return

        genres_filter = query_params.get('genres', [None])[0]
        if genres_filter:
            requested_genres = [g.strip() for g in genres_filter.split(',')]
            for g in requested_genres:
                if g not in VALID_GENRES:
                    self.send_error_response(400, f"Error: Invalid genre '{g}'")
                    return

            filtered_results = []
            for b in results:
                book_genres = [g.upper() for g in b['genres']]
                if any(req_g.upper() in book_genres for req_g in requested_genres):
                    filtered_results.append(b)
            results = filtered_results

        books_logger.info(f"Fetching books list")
        books_logger.debug(f"Found {len(results)} books matching criteria")

        if count_only:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": len(results)}).encode())
            return

        sorted_results = sorted(results, key=lambda x: x['title'].lower())
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"result": sorted_results}).encode())

    def handle_get_single_book(self, query_params):
        id_param = query_params.get('id', [None])[0]
        if id_param is None:
            self.send_error_response(400, "Error: id parameter is missing")
            return

        try:
            book_id = int(id_param)
        except ValueError:
            self.send_error_response(400, "Error: id must be a number")
            return

        if book_id in books_db:
            books_logger.info(f"Fetching book id {book_id}")
            books_logger.debug(f"Successfully fetched book id {book_id}")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": books_db[book_id]}).encode())
        else:
            self.send_error_response(404, f"Error: no such book with id {book_id}")

    def _do_POST(self):
        global next_id
        parsed_url = urlparse(self.path)

        if parsed_url.path == '/book':
            connect_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(connect_length)
            book_data = json.loads(post_data.decode('utf-8'))

            books_logger.info(f"Attempting to create a new book: {book_data['title']}")

            incoming_title_lower = book_data['title'].lower()
            for existing_book in books_db.values():
                if existing_book['title'].lower() == incoming_title_lower:
                    self.send_error_response(409,
                                             f"Error: Book with the title [{book_data['title']}] already exists in the system")
                    return

            if not (1940 <= book_data['year'] <= 2100):
                self.send_error_response(409,
                                         f"Error: Can't create new Book that its year [{book_data['year']}] is not in the accepted range [1940 -> 2100]")
                return

            if book_data['price'] <= 0:
                self.send_error_response(409, "Error: Can't create new Book with negative price")
                return

            new_id = next_id
            book_data['id'] = new_id
            books_db[new_id] = book_data
            next_id += 1

            books_logger.debug(f"Book [{new_id}] created successfully")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": new_id}).encode())

    def _do_PUT(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        if parsed_url.path == '/logs/level':
            logger_name = query_params.get('logger-name', [None])[0]
            logger_level = query_params.get('logger-level', [None])[0]

            if logger_name not in ['request-logger', 'books-logger']:
                self.send_error_response(400, "Error: Invalid logger-name")
                return

            if logger_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
                self.send_error_response(400, "Error: Invalid logger-level")
                return

            logger = logging.getLogger(logger_name)
            logger.setLevel(logger_level)

            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(logger_level.encode())
            return

        if parsed_url.path == '/book':
            id_param = query_params.get('id', [None])[0]
            price_param = query_params.get('price', [None])[0]

            if id_param is None:
                self.send_error_response(400, "Error: id parameter is missing")
                return

            try:
                book_id = int(id_param)
            except ValueError:
                self.send_error_response(400, "Error: id must be a number")
                return

            books_logger.info(f"Attempting to update price for book id {book_id}")

            if book_id not in books_db:
                self.send_error_response(404, f"Error: no such book with id {book_id}")
                return

            new_price = None
            if price_param is not None:
                try:
                    new_price = float(price_param)
                except ValueError:
                    self.send_error_response(400, "Error: price must be a number")
                    return
            else:
                try:
                    connect_length = int(self.headers.get('Content-Length', 0))
                    if connect_length > 0:
                        put_data = self.rfile.read(connect_length)
                        body_data = json.loads(put_data.decode('utf-8'))
                        new_price = float(body_data['price'])
                except (json.JSONDecodeError, KeyError, ValueError):
                    self.send_error_response(400, "Error: price parameter is missing or invalid")
                    return

            if new_price is None or new_price <= 0:
                self.send_error_response(409, "Error: price must be positive")
                return

            old_price = books_db[book_id]['price']
            books_db[book_id]['price'] = new_price

            books_logger.debug(f"Price of book [{book_id}] successfully updated from {old_price} to {new_price}")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": old_price}).encode())

    def _do_DELETE(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        if parsed_url.path == '/book':
            id_param = query_params.get('id', [None])[0]
            if id_param is None:
                self.send_error_response(400, "Error: id parameter is missing")
                return

            try:
                book_id = int(id_param)
            except ValueError:
                self.send_error_response(400, "Error: id must be a number")
                return

            books_logger.info(f"Attempting to delete book id {book_id}")

            if book_id not in books_db:
                self.send_error_response(404, f"Error: no such book with id {book_id}")
                return

            del books_db[book_id]

            books_logger.debug(f"Book [{book_id}] deleted successfully")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"result": book_id}).encode())


def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, BookServerHandler)
    print(f"Starting server on port {PORT}...")
    httpd.serve_forever()


if __name__ == '__main__':
    run_server()
