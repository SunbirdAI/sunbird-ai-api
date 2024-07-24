import os

from dotenv import load_dotenv
from locust import HttpUser, SequentialTaskSet, between, task

load_dotenv()


class UserBehavior(SequentialTaskSet):
    @task
    def nllb_translate(self):
        url = "https://api.sunbird.ai/tasks/nllb_translate"
        token = os.getenv("AUTH_TOKEN")
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        data = {
            "source_language": "eng",
            "target_language": "lug",
            "text": "Are we going for soccer today?",
        }

        # response = requests.post(url, headers=headers, json=data)

        self.client.post("/nllb_translate", headers=headers, json=data)

    @task
    def stop(self):
        self.interrupt()


class WebsiteUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(1, 5)

    def on_start(self):
        print("Starting test")

    def on_stop(self):
        print("Stopping test")
