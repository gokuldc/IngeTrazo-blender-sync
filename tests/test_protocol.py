import json
import unittest

class TestProtocol(unittest.TestCase):
    def test_hello_message(self):
        msg = {
            "protocol": "ingetrazo-blender-sync",
            "version": 1,
            "message": "hello",
            "client": "test-client"
        }
        encoded = json.dumps(msg) + "\\n"
        decoded = json.loads(encoded.strip())
        self.assertEqual(decoded["message"], "hello")
        self.assertEqual(decoded["client"], "test-client")

    def test_object_update(self):
        msg = {
            "protocol": "ingetrazo-blender-sync",
            "version": 1,
            "message": "object_update",
            "revision": 42,
            "object": {
                "id": "uuid-1234",
                "name": "Wall",
                "type": "group",
                "transform": [1.0] * 16,
                "geometry": {
                    "vertices": [[0,0,0], [1,0,0], [1,1,0], [0,1,0]],
                    "faces": [[0, 1, 2, 3]]
                },
                "metadata": {
                    "class": "IfcWall"
                }
            }
        }
        encoded = json.dumps(msg) + "\\n"
        decoded = json.loads(encoded.strip())
        self.assertEqual(decoded["object"]["id"], "uuid-1234")
        self.assertEqual(len(decoded["object"]["geometry"]["vertices"]), 4)

if __name__ == '__main__':
    unittest.main()
