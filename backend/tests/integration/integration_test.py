import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.app.db import get_db, async_session


@pytest.fixture(scope="module")
def test_client():
    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client


@pytest.fixture
def test_image_bytes():
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def create_test_user(test_client):
    def _create_user(username: str, password: str = "password123"):
        response = test_client.post("/register", json={"username": username, "password": password})

        if response.status_code == 201:
            return True
        elif response.status_code == 400 and response.json().get("detail") == "Username already exists":
            return False
        else:
            pytest.fail(f"Failed to create user {username}: {response.status_code} - {response.text}")

    yield _create_user


@pytest.fixture
def auth_headers(test_client, create_test_user):
    def _get_headers(username: str = "testuser", password: str = "password123"):
        create_test_user(username, password)

        response = test_client.post("/login", json={"username": username, "password": password})
        assert response.status_code == 200, f"Login failed for {username}: {response.text}"

        cookies = response.cookies
        session_token = cookies.get('session_token')
        assert session_token is not None, "No session token received"

        return {"Cookie": f"session_token={session_token}"}

    return _get_headers


class TestEndToEndAuthentication:
    def test_complete_auth_flow(self, test_client, create_test_user):
        create_test_user("e2e_user", "securepass123")

        login_response = test_client.post(
            "/login",
            json={"username": "e2e_user", "password": "securepass123"}
        )
        assert login_response.status_code == 200
        assert login_response.json() == {"username": "e2e_user"}

        session_cookie = login_response.cookies.get("session_token")
        assert session_cookie is not None
        assert len(session_cookie) > 0

        protected_response = test_client.get(
            "/user-info",
            cookies={"session_token": session_cookie}
        )
        assert protected_response.status_code == 200
        user_info = protected_response.json()
        assert "user_id" in user_info
        assert user_info["username"] == "e2e_user"

        logout_response = test_client.post(
            "/logout",
            cookies={"session_token": session_cookie}
        )
        assert logout_response.status_code == 200
        assert logout_response.json() == {"message": "Logged out successfully"}

        post_logout_response = test_client.get(
            "/user-info",
            cookies={"session_token": session_cookie}
        )
        assert post_logout_response.status_code == 401

    def test_register_validation_errors(self, test_client):
        response = test_client.post(
            "/register",
            json={"username": "ab", "password": "password123"}
        )
        assert response.status_code == 422
        assert "username" in response.text.lower()

        response = test_client.post(
            "/register",
            json={"username": "validuser", "password": "12345"}
        )
        assert response.status_code == 422
        assert "password" in response.text.lower()

        test_client.post("/register", json={"username": "duplicate", "password": "pass123"})
        response = test_client.post(
            "/register",
            json={"username": "duplicate", "password": "pass123"}
        )
        assert response.status_code == 400
        assert "already exists" in response.text.lower()

    def test_login_lockout(self, test_client, create_test_user):
        create_test_user("lockout_user", "correctpass")

        for i in range(2):
            response = test_client.post(
                "/login",
                json={"username": "lockout_user", "password": "wrongpass"}
            )
            assert response.status_code == 401

        response = test_client.post(
            "/login",
            json={"username": "lockout_user", "password": "wrongpass"}
        )
        assert response.status_code == 423
        assert "locked" in response.text.lower()

        response = test_client.post(
            "/login",
            json={"username": "lockout_user", "password": "correctpass"}
        )
        assert response.status_code == 423

    def test_session_persistence_across_requests(self, test_client, create_test_user):
        create_test_user("session_user", "password")
        login_response = test_client.post("/login", json={"username": "session_user", "password": "password"})
        session_token = login_response.cookies.get("session_token")

        for _ in range(5):
            response = test_client.get("/user-info", cookies={"session_token": session_token})
            assert response.status_code == 200


class TestEndToEndImageProcessing:
    def test_basic_image_processing_flow(self, test_client, test_image_bytes):
        pipeline = {
            "nodes": [
                {"type": "blur", "params": {"radius": 5}}
            ]
        }

        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        response = test_client.post("/process-image", files=files, data=data)
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

        result_img = Image.open(io.BytesIO(response.content))
        assert result_img.format == "PNG"
        assert result_img.size == (100, 100)

    def test_pipeline_with_multiple_nodes(self, test_client, test_image_bytes):
        pipeline = {
            "nodes": [
                {"type": "blur", "params": {"radius": 3}},
                {"type": "noise", "params": {"intensity": 15, "seed": 42}},
                {"type": "make_mask", "params": {"threshold": 128}}
            ]
        }

        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        response = test_client.post("/process-image", files=files, data=data)
        assert response.status_code == 200

        result_img = Image.open(io.BytesIO(response.content))
        assert result_img.mode in ("RGB", "L")

    def test_preview_specific_node(self, test_client, test_image_bytes):
        pipeline = {
            "nodes": [
                {"id": "blur1", "type": "blur", "params": {"radius": 3}},
                {"id": "noise1", "type": "noise", "params": {"intensity": 20}}
            ]
        }

        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {
            "pipeline": json.dumps(pipeline),
            "preview_node_id": "blur1"
        }

        response = test_client.post("/process-image", files=files, data=data)
        assert response.status_code == 200

    def test_pipeline_with_branches(self, test_client, test_image_bytes):
        pipeline = {
            "nodes": [
                {"id": "blur1", "type": "blur", "params": {"radius": 5}},
                {"id": "noise1", "type": "noise", "branch": "side", "params": {"intensity": 10}},
                {"id": "blur2", "type": "blur", "branch": "side", "params": {"radius": 2}}
            ],
            "branchSources": {"side": "blur1"}
        }

        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        response = test_client.post("/process-image", files=files, data=data)
        assert response.status_code == 200

    def test_pipeline_with_mask(self, test_client, test_image_bytes):
        pipeline = {
            "nodes": [
                {"id": "mask1", "type": "make_mask", "params": {"threshold": 100}},
                {"id": "blur1", "type": "blur", "params": {"radius": 5, "maskNodeId": "mask1"}}
            ]
        }

        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        response = test_client.post("/process-image", files=files, data=data)
        assert response.status_code == 200

    def test_invalid_pipeline_returns_error(self, test_client, test_image_bytes):
        pipeline = {
            "nodes": [
                {"id": "blur1", "type": "blur", "params": {"maskNodeId": "nonexistent"}}
            ]
        }

        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        response = test_client.post("/process-image", files=files, data=data)
        assert response.status_code == 400
        assert "Mask node id not found" in response.text

    def test_oversized_image_rejected(self, test_client):
        large_data = b"x" * (25 * 1024 * 1024 + 1)

        pipeline = {"nodes": [{"type": "blur"}]}
        files = {"image": ("large.png", large_data, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        response = test_client.post("/process-image", files=files, data=data)
        assert response.status_code == 413
        assert "exceeds maximum size" in response.text.lower()


class TestEndToEndPipelineCRUD:
    def test_complete_pipeline_crud_flow(self, test_client, create_test_user):
        create_test_user("crud_user", "password")
        login_response = test_client.post("/login", json={"username": "crud_user", "password": "password"})
        session_cookie = login_response.cookies.get("session_token")
        cookies = {"session_token": session_cookie}

        create_payload = {
            "name": "my_pipeline",
            "nodes": [
                {"id": "blur1", "type": "blur", "params": {"radius": 5}},
                {"id": "noise1", "type": "noise", "params": {"intensity": 20, "seed": 42}}
            ]
        }

        create_response = test_client.post(
            "/pipelines",
            json=create_payload,
            cookies=cookies
        )
        assert create_response.status_code == 201
        pipeline_id = create_response.json()["id"]
        assert pipeline_id is not None

        get_response = test_client.get(
            "/pipelines/my_pipeline",
            cookies=cookies
        )
        assert get_response.status_code == 200
        pipeline_data = get_response.json()
        assert pipeline_data["id"] == pipeline_id
        assert pipeline_data["name"] == "my_pipeline"
        assert "pipeline_data" in pipeline_data
        assert len(pipeline_data["pipeline_data"]["nodes"]) == 2

        list_response = test_client.get("/pipelines", cookies=cookies)
        assert list_response.status_code == 200
        pipelines = list_response.json()
        assert len(pipelines) >= 1
        assert any(p["name"] == "my_pipeline" for p in pipelines)

        update_payload = {
            "name": "my_pipeline",
            "nodes": [
                {"id": "blur1", "type": "blur", "params": {"radius": 10}},
                {"id": "noise1", "type": "noise", "params": {"intensity": 50, "seed": 99}},
                {"id": "mask1", "type": "make_mask", "params": {"threshold": 200}}
            ],
            "branchSources": {"main": "original"}
        }

        update_response = test_client.post(
            "/pipelines",
            json=update_payload,
            cookies=cookies
        )
        assert update_response.status_code == 201
        assert update_response.json()["id"] == pipeline_id

        get_updated_response = test_client.get(
            "/pipelines/my_pipeline",
            cookies=cookies
        )
        assert get_updated_response.status_code == 200
        updated_nodes = get_updated_response.json()["pipeline_data"]["nodes"]
        assert len(updated_nodes) == 3
        assert updated_nodes[0]["params"]["radius"] == 10

        delete_response = test_client.delete(
            "/pipelines/my_pipeline",
            cookies=cookies
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["message"] == "Pipeline deleted successfully"

        get_deleted_response = test_client.get(
            "/pipelines/my_pipeline",
            cookies=cookies
        )
        assert get_deleted_response.status_code == 404

    def test_pipeline_isolation_between_users(self, test_client, create_test_user):
        create_test_user("user_a", "password")
        login_a = test_client.post("/login", json={"username": "user_a", "password": "password"})
        cookie_a = login_a.cookies.get("session_token")

        test_client.post(
            "/pipelines",
            json={"name": "a_pipeline", "nodes": [{"type": "blur"}]},
            cookies={"session_token": cookie_a}
        )

        create_test_user("user_b", "password")
        login_b = test_client.post("/login", json={"username": "user_b", "password": "password"})
        cookie_b = login_b.cookies.get("session_token")

        list_b = test_client.get("/pipelines", cookies={"session_token": cookie_b})
        pipelines_b = list_b.json()
        assert not any(p["name"] == "a_pipeline" for p in pipelines_b)

        get_b = test_client.get(
            "/pipelines/a_pipeline",
            cookies={"session_token": cookie_b}
        )
        assert get_b.status_code == 404

        delete_b = test_client.delete(
            "/pipelines/a_pipeline",
            cookies={"session_token": cookie_b}
        )
        assert delete_b.status_code == 404


class TestEndToEndIntegrated:
    def test_authenticated_image_processing(self, test_client, test_image_bytes, create_test_user, auth_headers):
        create_test_user("auth_proc", "password")
        headers = auth_headers("auth_proc", "password")

        pipeline = {"nodes": [{"type": "blur", "params": {"radius": 5}}]}
        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        response = test_client.post("/process-image", files=files, data=data, headers=headers)
        assert response.status_code == 200

        save_response = test_client.post(
            "/pipelines",
            json={"name": "saved_pipeline", "nodes": [{"type": "blur", "params": {"radius": 8}}]},
            headers=headers
        )
        assert save_response.status_code == 201

    def test_unauthenticated_cannot_save_pipelines(self, test_client):
        response = test_client.post(
            "/pipelines",
            json={"name": "unauth_pipeline", "nodes": []},
            cookies={"session_token": "unauth"}
        )
        assert response.status_code == 401

    def test_full_workflow_with_saved_pipeline(self, test_client, test_image_bytes, create_test_user, auth_headers):
        create_test_user("full_flow", "password")
        headers = auth_headers("full_flow", "password")

        pipeline_config = {
            "name": "production_pipeline",
            "nodes": [
                {"id": "blur_main", "type": "blur", "params": {"radius": 4}},
                {"id": "noise_mid", "type": "noise", "params": {"intensity": 15, "seed": 123}},
                {"id": "mask_edge", "type": "make_mask", "params": {"threshold": 150, "invert": True}}
            ]
        }

        save_response = test_client.post(
            "/pipelines",
            json=pipeline_config,
            headers=headers
        )
        assert save_response.status_code == 201

        get_response = test_client.get(
            "/pipelines/production_pipeline",
            headers=headers
        )
        assert get_response.status_code == 200
        saved_nodes = get_response.json()["pipeline_data"]["nodes"]

        process_payload = {"nodes": saved_nodes}
        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(process_payload)}

        process_response = test_client.post("/process-image", files=files, data=data)
        assert process_response.status_code == 200

        delete_response = test_client.delete(
            "/pipelines/production_pipeline",
            headers=headers
        )
        assert delete_response.status_code == 200

    def test_concurrent_users_processing(self, test_client, test_image_bytes, create_test_user):
        users = ["concurrent_1", "concurrent_2", "concurrent_3"]
        session_cookies = {}

        for username in users:
            create_test_user(username, "password")
            login_resp = test_client.post("/login", json={"username": username, "password": "password"})
            assert login_resp.status_code == 200
            session_cookies[username] = login_resp.cookies.get("session_token")

            save_resp = test_client.post(
                "/pipelines",
                json={"name": f"{username}_pipeline", "nodes": [{"type": "blur"}]},
                cookies={"session_token": session_cookies[username]}
            )
            assert save_resp.status_code == 201

        pipeline = {"nodes": [{"type": "noise", "params": {"intensity": 10}}]}
        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        for username, cookie in session_cookies.items():
            response = test_client.post(
                "/process-image",
                files=files,
                data=data,
                cookies={"session_token": cookie}
            )
            assert response.status_code == 200

            list_resp = test_client.get(
                "/pipelines",
                cookies={"session_token": cookie}
            )
            assert list_resp.status_code == 200
            pipeline_names = [p["name"] for p in list_resp.json()]
            assert f"{username}_pipeline" in pipeline_names