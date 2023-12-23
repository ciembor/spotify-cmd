from config import Config

class SocketDataHandler:
    config = Config.get_instance()
    SOCKET_BUFFER_SIZE = config.socket_buffer_size
    END_OF_MESSAGE = b"<END_OF_MESSAGE>"

    @staticmethod
    def send_data(connection, message):
        if message:
            response = message.encode()
            for i in range(0, len(response), SocketDataHandler.SOCKET_BUFFER_SIZE):
                connection.sendall(response[i:i+SocketDataHandler.SOCKET_BUFFER_SIZE])
            connection.sendall(SocketDataHandler.END_OF_MESSAGE)

    @staticmethod
    def receive_data(connection):
        data = b""
        end_of_message_received = False

        while True:
            packet = connection.recv(SocketDataHandler.SOCKET_BUFFER_SIZE)
            data += packet

            if SocketDataHandler.END_OF_MESSAGE in data:
                end_of_message_received = True
                break

        if end_of_message_received:
            data = data.replace(SocketDataHandler.END_OF_MESSAGE, b"")
            return data.decode()
        else:
            return None
