from socket import socket, AF_INET, SOCK_STREAM


import socket
from socket import AF_INET, SOCK_STREAM

def request_current_from_ammeter(port: int, command: bytes, timeout=4) -> float:
    try:
        with socket.socket(AF_INET, SOCK_STREAM) as s:
            s.settimeout(timeout)  # set timeout
            s.connect(('localhost', port))
            s.sendall(command)
            data = s.recv(1024)

            if data:
                encoded_data = data.decode('utf-8').strip()
                return float(encoded_data)

            else:
                return -1.0

    except socket.timeout:
        return -2.0

    except Exception as e:
        return -3.0

