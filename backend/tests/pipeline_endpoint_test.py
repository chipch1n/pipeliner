from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.main import app
from backend.tests.util.db_util import setup_mock_execute

mocked_db = AsyncMock(spec=AsyncSession)

@pytest.fixture
def mock_db():
    mocked_db.reset_mock()
    return mocked_db

@pytest.fixture
def test_client():
    async def override_get_db():
        return mocked_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

def mock_current_user_override(return_user_id=1):
    async def mock_get_current_user(request=None, response=None, db=None):
        return return_user_id
    app.dependency_overrides[get_current_user] = mock_get_current_user

from backend.app.main import get_current_user

class TestSavePipeline:
    def test_save_new_pipeline_success(self, test_client, mock_db):
        mock_current_user_override(1)

        setup_mock_execute(mock_db, None)

        payload = {
            "name": "my_pipeline",
            "nodes": [
                {"id": "blur1", "type": "blur", "params": {"radius": 5}}
            ]
        }

        response = test_client.post("/pipelines", json=payload)

        assert response.status_code == 201
        assert response.json()["id"] is None

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    def test_save_new_pipeline_minimal_nodes(self, test_client, mock_db):
        mock_current_user_override(1)

        setup_mock_execute(mock_db, None)

        payload = {
            "name": "empty_pipeline",
            "nodes": []
        }

        response = test_client.post("/pipelines", json=payload)

        assert response.status_code == 201
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    def test_update_existing_pipeline(self, test_client, mock_db):
        mock_current_user_override(1)

        existing_pipeline = MagicMock()
        existing_pipeline.id = 42
        existing_pipeline.name = "my_pipeline"
        existing_pipeline.pipeline_data = {"nodes": []}
        existing_pipeline.updated_at = None

        setup_mock_execute(mock_db, existing_pipeline)

        payload = {
            "name": "my_pipeline",
            "nodes": [
                {"id": "noise1", "type": "noise", "params": {"intensity": 30}}
            ],
            "branchSources": {"main": "original"}
        }

        response = test_client.post("/pipelines", json=payload)

        assert response.status_code == 201
        assert response.json()["id"] == 42

        assert existing_pipeline.pipeline_data == {"nodes": payload["nodes"], "branch_sources": payload["branchSources"]}
        mock_db.commit.assert_called()

    def test_save_pipeline_unauthorized(self, test_client):
        payload = {"name": "test", "nodes": []}

        response = test_client.post("/pipelines", json=payload)

        assert response.status_code == 401

    def test_save_pipeline_invalid_name_empty(self, test_client, mock_db):
        mock_current_user_override(1)

        payload = {"name": "", "nodes": []}

        response = test_client.post("/pipelines", json=payload)

        assert response.status_code == 422

    def test_save_pipeline_missing_nodes(self, test_client, mock_db):
        mock_current_user_override(1)

        payload = {"name": "test"}

        response = test_client.post("/pipelines", json=payload)

        assert response.status_code == 422

class TestGetPipeline:
    def test_get_pipeline_success(self, test_client, mock_db):
        mock_current_user_override(1)

        pipeline = MagicMock()
        pipeline.id = 1
        pipeline.name = "my_pipeline"
        pipeline.pipeline_data = {"nodes": [{"type": "blur", "params": {"radius": 5}}]}

        setup_mock_execute(mock_db, pipeline)

        response = test_client.get("/pipelines/my_pipeline")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "my_pipeline"
        assert data["pipeline_data"] == {"nodes": [{"type": "blur", "params": {"radius": 5}}]}

    def test_get_pipeline_not_found(self, test_client, mock_db):
        mock_current_user_override(1)

        setup_mock_execute(mock_db, None)

        response = test_client.get("/pipelines/nonexistent")

        assert response.status_code == 404
        assert response.json()["detail"] == "Pipeline not found"

    def test_get_pipeline_unauthorized(self, test_client):
        response = test_client.get("/pipelines/any")

        assert response.status_code == 401

class TestListPipelines:
    def test_list_pipelines_empty(self, test_client, mock_db):
        mock_current_user_override(1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = test_client.get("/pipelines")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_pipelines_multiple(self, test_client, mock_db):
        mock_current_user_override(1)

        pipeline1 = MagicMock()
        pipeline1.id = 1
        pipeline1.name = "pipeline_a"

        pipeline2 = MagicMock()
        pipeline2.id = 2
        pipeline2.name = "pipeline_b"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pipeline1, pipeline2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = test_client.get("/pipelines")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["name"] == "pipeline_a"
        assert data[1]["id"] == 2
        assert data[1]["name"] == "pipeline_b"

    def test_list_pipelines_unauthorized(self, test_client):
        response = test_client.get("/pipelines")

        assert response.status_code == 401

class TestDeletePipeline:
    def test_delete_pipeline_success(self, test_client, mock_db):
        mock_current_user_override(1)

        pipeline = MagicMock()
        pipeline.id = 1
        pipeline.name = "to_delete"

        setup_mock_execute(mock_db, pipeline)

        response = test_client.delete("/pipelines/to_delete")

        assert response.status_code == 200
        assert response.json() == {"message": "Pipeline deleted successfully"}

        mock_db.delete.assert_called_once_with(pipeline)
        mock_db.commit.assert_called()

    def test_delete_pipeline_not_found(self, test_client, mock_db):
        mock_current_user_override(1)

        setup_mock_execute(mock_db, None)

        response = test_client.delete("/pipelines/nonexistent")

        assert response.status_code == 404
        assert response.json()["detail"] == "Pipeline not found"
        mock_db.delete.assert_not_called()

    def test_delete_pipeline_unauthorized(self, test_client):
        response = test_client.delete("/pipelines/any")

        assert response.status_code == 401

class TestPipelineResponseModels:
    def test_pipeline_list_item_model(self, test_client, mock_db):
        mock_current_user_override(1)

        pipeline = MagicMock()
        pipeline.id = 5
        pipeline.name = "test_pipeline"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pipeline]
        mock_db.execute = AsyncMock(return_value=mock_result)

        response = test_client.get("/pipelines")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "id" in data[0]
        assert "name" in data[0]
        assert "pipeline_data" not in data[0]

    def test_pipeline_response_model(self, test_client, mock_db):
        mock_current_user_override(1)

        pipeline = MagicMock()
        pipeline.id = 5
        pipeline.name = "test_pipeline"
        pipeline.pipeline_data = {"nodes": [{"type": "blur"}]}

        setup_mock_execute(mock_db, pipeline)

        response = test_client.get("/pipelines/test_pipeline")

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "name" in data
        assert "pipeline_data" in data
        assert data["pipeline_data"] == {"nodes": [{"type": "blur"}]}