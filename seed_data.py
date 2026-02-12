import asyncio
import random
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database.db import async_session_maker
from app.models.monitoring import EndpointLog
from app.models.users import User


async def seed_data():
    async with async_session_maker() as session:
        # Check if user exists
        username = "eve@eve.com"
        result = await session.execute(select(User).filter(User.email == username))
        user = result.scalars().first()

        if not user:
            print(f"User {username} not found. Please create the user first.")
            return

        print(f"Seeding data for {username}...")

        endpoints = ["/v1/translate", "/v1/stt", "/v1/tts", "/v1/language_id"]

        # Generate logs for the last 30 days
        logs = []
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        current_date = start_date
        while current_date <= end_date:
            # Random number of requests per day (10 to 100)
            daily_requests = random.randint(10, 100)

            for _ in range(daily_requests):
                # Random time within the day
                log_time = current_date + timedelta(
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                    seconds=random.randint(0, 59),
                )

                endpoint = random.choice(endpoints)

                # Random latency (0.1s to 2.0s)
                latency = random.uniform(0.1, 2.0)

                log = EndpointLog(
                    username=user.username,
                    organization=user.organization,
                    endpoint=endpoint,
                    time_taken=latency,
                    date=log_time,
                )
                logs.append(log)

            current_date += timedelta(days=1)

        session.add_all(logs)
        await session.commit()
        print(f"Successfully added {len(logs)} logs.")


if __name__ == "__main__":
    asyncio.run(seed_data())
