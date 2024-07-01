## Creating a WhatsApp App Using the WhatsApp Cloud API

This documentation provides a comprehensive guide to creating a WhatsApp app using the WhatsApp Cloud API, from setting up the app on the Facebook Developer Portal to deploying it with FastAPI webhooks. This step-by-step guide will help you navigate through the process to get your app live.

### Prerequisites

1.  Facebook Developer Account:  Ensure you have a Facebook Developer account.
2.  WhatsApp Business Account:  Create a WhatsApp Business Account.
3.  FastAPI:  Familiarity with FastAPI for creating webhooks.
4.  Python Environment:  Set up a Python environment with FastAPI installed.

 Step 1: Setting Up Your App on the Facebook Developer Portal

 1.1 Create a New App

1. Go to the [Facebook Developer Portal](https://developers.facebook.com/).
2. Click on "My Apps" in the top right corner.
3. Click on "Create App".
4. Select "Business" as the app type and click "Next".
5. Fill in the required details:
   -  App Display Name 
   -  App Contact Email 
6. Click "Create App ID".

 1.2 Configure the App

1. Once the app is created, go to the dashboard.
2. Under "Add a Product", find WhatsApp and click "Set Up".
3. Navigate to "Getting Started" under the WhatsApp product.
4. Select the WhatsApp Business Account you want to link.

 Step 2: Setting Up WhatsApp Business API

 2.1 Generate an Access Token

1. Under "Getting Started", click on "Generate Access Token".
2. Save this token securely as it will be used for authentication in your API requests.

 2.2 Add a Phone Number

1. In the "Getting Started" section, add a phone number to your WhatsApp Business Account.
2. Verify the phone number by following the instructions provided.

 Step 3: Setting Up FastAPI Webhooks

 3.1 Create a FastAPI Project

1. Create a new directory for your FastAPI project and navigate into it:(For our case we used the existing Sunbird-ai-api)

 3.2 Create the FastAPI App

1. Used a file named `tasks.py` in the routers:
   ```python

   @app.post("/webhook")
   async def webhook(event: WebhookEvent):
         Process the webhook event here
       print(event)
       return {"status": "received"}

   @app.get("/")
   async def root():
       return {"message": "Hello, this is your WhatsApp API webhook"}
   ```

 3.3 Run the FastAPI App

1. Run your FastAPI app:
   ```bash
   uvicorn main:app --reload
   ```

 Step 4: Setting Up Webhooks in Facebook Developer Portal

 4.1 Verify the Webhook

1. Go back to the Facebook Developer Portal.
2. Navigate to the "Webhooks" section under the WhatsApp product.
3. Click on "Add Callback URL" and enter the following:
   -  Callback URL:  `http://<your-server-ip>:8000/webhook`
   -  Verify Token:  A token of your choice for verification (e.g., `my_verify_token`)

4. Add a route in your FastAPI app to handle verification:
   ```python
   @app.get("/webhook")
   async def verify(request: Request):
       verify_token = "my_verify_token"
       mode = request.query_params.get("hub.mode")
       token = request.query_params.get("hub.verify_token")
       challenge = request.query_params.get("hub.challenge")

       if mode and token:
           if mode == "subscribe" and token == verify_token:
               return int(challenge)
           else:
               return {"status": "forbidden"}
   ```

 4.2 Subscribe to Webhook Events

1. Once the callback URL is verified, subscribe to the required webhook events (e.g., messages).

 Step 5: Testing and Deployment

 5.1 Testing Locally
 1. We need to deploy for a live webhook.

 5.2 Deploying the FastAPI App

1. Deploy your FastAPI app to a cloud provider or server of your choice (e.g., AWS, Heroku, DigitalOcean) For our case we are using GCP cloud run instance.
2. Update the callback URL in the Facebook Developer Portal to point to your deployed app.

 Step 6: Going Live

1. Ensure that your WhatsApp Business Account is verified.
2. Test the entire flow from sending a message to receiving and processing the webhook.
3. Monitor your app for any issues and ensure it handles all incoming messages correctly.

 Conclusion

You have successfully created a WhatsApp app using the WhatsApp Cloud API, set up webhooks with FastAPI, and deployed your application. This guide covered all the essential steps to get your app live and running. Ensure to follow best practices for security and scalability as you move forward.
