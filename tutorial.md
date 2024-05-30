# Sunbird AI API Tutorial
This page describes how to use the Sunbird AI API and includes code samples in Python.


## Part 1: How to authenticate
1. If you don't already have an account, create one at https://api.sunbird.ai/register and login.
2. Go to the [tokens page](https://api.sunbird.ai/tokens) to get your access token which you'll use to authenticate

## Part 2: How to call the translation endpoint
Refer to the sample code below. Replace `{access_token}` with the token you received above.


```python
import os
import requests

from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/nllb_translate"
access_token = os.getenv("AUTH_TOKEN")
headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

data = {
    "source_language": "lug",
    "target_language": "eng",
    "text": "Ekibiina ekiddukanya omuzannyo gw’emisinde mu ggwanga ekya Uganda Athletics Federation kivuddeyo nekitegeeza nga lawundi esooka eyemisinde egisunsulamu abaddusi abanakiika mu mpaka ezenjawulo ebweru w’eggwanga egya National Athletics Trials nga bwegisaziddwamu.",
}

response = requests.post(url, headers=headers, json=data)

print(response.json())
```

The dictionary below represents the language codes available now for the translate endpoint

```python
language_codes: {
    "English": "eng",
    "Luganda": "lug",
    "Runyankole": "nyn",
    "Acholi": "ach",
    "Ateso": "teo",
    "Lugbara": "lgg"
}
```

## Part 3: How to call the speech-to-text endpoint
Refer to the sample code below. Replace `{access_token}` with the token you got from the `/auth/token` endpoint. And replace `/path/to/audio_file` with the path to the audio file you want to transcribe and `FILE_NAME` with audio filename. 

```python
import os
import requests

from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/stt"
access_token = os.getenv("AUTH_TOKEN")
headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
}

files = {
    "audio": (
        "FILE_NAME",
        open("/path/to/audio_file", "rb"),
        "audio/mpeg",
    ),
}
data = {
    "language": "lug",
    "adapter": "lug",
}

response = requests.post(url, headers=headers, files=files, data=data)

print(response.json())
```

## Part 4: How to call the summary endpoint

```python
import os

import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/summarise"
token = os.getenv("AUTH_TOKEN")
headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

text = (
    "ndowooza yange ku baana bano abato abatalina tufuna funa ya uganda butuufu "
    "eserbamby omwana oyo bingi bye yeegomba okuva mu buto bwe ate by'atasobola "
    "kwetuusaako bw'afuna mu naawumuwaamagezi nti ekya mazima nze kaboyiaadeyaatei "
    "ebintu kati bisusse mu uganda wano ebyegombebw'omwana by'atasobola kwetuusaako "
    "ng'ate abazadde nabo bambi bwe beetunulamubamufuna mpola tebasobola kulabirira "
    "mwana oyo bintu by'ayagala ekivaamu omwana akemererwan'ayagala omulenzi omulenzi "
    "naye n'atoba okuatejukira ba mbi ba tannategeera bigambo bya kufuna famire fulani "
    "bakola kyagenda layivu n'afuna embuto eky'amazima nze mbadde nsaba be kikwata "
    "govenment sembera embeera etuyisa nnyo abaana ne tubafaako embeera gwe nyiga gwa "
    "omuzadde olina olabirira maama we olina olabirira n'abato kati kano akasuumuseemu "
    "bwe ka kubulako ne keegulirayooba kapalaobakakioba tokyabisobola ne keyiiyabatuyambe "
    "buduufuembeera bagikyusa mu tulemye"
)

data = {"text": text}

response = requests.post(url, headers=headers, json=data)

print(response.json())
```

## Part 5: How to call the language_id endpoint

```python
import os

import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/language_id"
token = os.getenv("AUTH_TOKEN")
headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

text = "ndowooza yange ku baana bano abato abatalina tufuna funa ya uganda butuufu"

data = {"text": text}

response = requests.post(url, headers=headers, json=data)

print(response.json())
```

You can refer to the [docs](https://api.sunbird.ai/docs) for more info about the endpoints.

## Feedback and Questions.
Don't hesitate to leave us any feedback or questions you have by opening an [issue in this repo](https://github.com/SunbirdAI/sunbird-ai-api/issues).
