from __future__ import annotations

import os
from locust import HttpUser, between, task


class AthleteSearchUser(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        self.search_term = os.getenv("LOAD_TEST_SEARCH_TERM", "dupont")

    @task(3)
    def home(self):
        self.client.get("/", name="home")

    @task(2)
    def app_bootstrap(self):
        self.client.get("/_stcore/health", name="st_health")

    @task(1)
    def search_like_user(self):
        self.client.get(f"/?search_term={self.search_term}", name="search_page")
