import os
import pytest
from unittest.mock import Mock, patch
from app.inference_services.user_preference import get_user_preference, save_user_preference, save_translation 

# Mock Firestore client
mock_firestore_client = Mock()

# Mock Firestore document
mock_document = Mock()

# Mock Firestore collection
mock_collection = Mock()
mock_collection.document.return_value = mock_document

# Mock Firestore client's collection method
mock_firestore_client.collection.return_value = mock_collection

# Mock Firestore document's get method
mock_document.get.return_value = mock_document

# Mock Firestore document's exists property
mock_document.exists = True

# Mock Firestore document's to_dict method
mock_document.to_dict.return_value = {'source_language': 'English', 'target_language': 'Luganda'}

@patch('app.inference_services.user_preference.firestore.client', return_value=mock_firestore_client)  
def test_get_user_preference(mock_firestore_client):
    source_language, target_language = get_user_preference('test_user_id')
    assert source_language == 'English'
    assert target_language == 'Luganda'

@patch('app.inference_services.user_preference.firestore.client', return_value=mock_firestore_client)  
def test_save_user_preference(mock_firestore_client):
    save_user_preference('test_user_id', 'English', 'Luganda')
    mock_collection.document.assert_called_once_with('test_user_id')
    mock_document.set.assert_called_once_with({'source_language': 'English', 'target_language': 'Luganda'})

@patch('app.inference_services.user_preference.firestore.client', return_value=mock_firestore_client)  
def test_save_translation(mock_firestore_client):
    save_translation('test_user_id', 'How are you', 'Oli otya', 'English', 'Luganda')
    mock_collection.add.assert_called_once()
