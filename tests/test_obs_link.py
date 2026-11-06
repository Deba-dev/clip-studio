"""Runs the real client against a small fake OBS speaking the v5 protocol."""
import json
import queue
import threading

from websockets.sync.server import serve

from clipstudio.obs import ObsClient, auth_string

SALT, CHALLENGE = "salty", "chal"


def fake_obs(password):
    seen = {}

    def handler(ws):
        hello = {"rpcVersion": 1}
        if password:
            hello["authentication"] = {"salt": SALT, "challenge": CHALLENGE}
        ws.send(json.dumps({"op": 0, "d": hello}))
        identify = json.loads(ws.recv())["d"]
        seen["subs"] = identify["eventSubscriptions"]
        if password and identify.get("authentication") != auth_string(password, SALT, CHALLENGE):
            ws.close(4009, "Authentication failed")
            return
        ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        request = json.loads(ws.recv())["d"]
        ws.send(json.dumps({"op": 7, "d": {"requestId": request["requestId"], "requestType": request["requestType"],
                                           "responseData": {"outputActive": False}}}))
        ws.send(json.dumps({"op": 5, "d": {"eventType": "RecordStateChanged", "eventData": {
            "outputState": "OBS_WEBSOCKET_OUTPUT_STARTED", "outputPath": "a.mkv"}}}))
        try:
            ws.recv()
        except Exception:
            pass

    server = serve(handler, "127.0.0.1", 0, subprotocols=["obswebsocket.json"])
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def connect(server, password):
    events, states = queue.Queue(), queue.Queue()
    client = ObsClient("127.0.0.1", server.socket.getsockname()[1], password,
                       lambda n, d: events.put((n, d)), lambda t, ok: states.put((t, ok)))
    client.start()
    return client, events, states


def test_login_and_events_with_password():
    server, seen = fake_obs("secret")
    client, events, states = connect(server, "secret")
    assert states.get(timeout=5) == ("Connected to OBS", True)
    assert events.get(timeout=5)[0] == "Reply:GetRecordStatus"
    name, data = events.get(timeout=5)
    assert name == "RecordStateChanged" and data["outputPath"] == "a.mkv"
    assert seen["subs"] == 64
    client.stop()
    server.shutdown()


def test_wrong_password_is_reported_clearly():
    server, _ = fake_obs("secret")
    client, _, states = connect(server, "nope")
    assert states.get(timeout=5) == ("OBS refused the WebSocket password", False)
    client.stop()
    server.shutdown()


def test_missing_password_is_reported_clearly():
    server, _ = fake_obs("secret")
    client, _, states = connect(server, "")
    assert "password" in states.get(timeout=5)[0]
    client.stop()
    server.shutdown()
