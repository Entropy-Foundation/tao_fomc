import unittest
from unittest.mock import patch, MagicMock
import json
import chat

class TestChatExtraction(unittest.TestCase):
    """Unit tests for chat.py interest rate extraction functionality."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.messages = chat.warmup()
    
    @patch('chat.ollama.chat')
    def test_rate_increase(self, mock_ollama_chat):
        """Test extraction of interest rate increase."""
        # Mock responses for the conversation flow
        mock_responses = [
            {'message': {'content': 'Yes'}},  # Initial question response
            {'message': {'content': 'The Federal Reserve raised the federal funds rate by 0.75 percentage points.'}},  # Sentence extraction
            {'message': {'content': '{"direction": "increase", "basis_points": 75}'}}  # JSON response
        ]
        mock_ollama_chat.side_effect = mock_responses
        
        article_text = "The Federal Reserve announced today that it has raised the federal funds rate by 0.75 percentage points to combat inflation."
        result = chat.extract(article_text, self.messages)
        
        self.assertEqual(result, 75)
        self.assertEqual(mock_ollama_chat.call_count, 3)
    
    @patch('chat.ollama.chat')
    def test_rate_decrease(self, mock_ollama_chat):
        """Test extraction of interest rate decrease."""
        # Mock responses for the conversation flow
        mock_responses = [
            {'message': {'content': 'Yes'}},  # Initial question response
            {'message': {'content': 'The Federal Reserve cut interest rates by 0.50 percentage points.'}},  # Sentence extraction
            {'message': {'content': '{"direction": "decrease", "basis_points": 50}'}}  # JSON response
        ]
        mock_ollama_chat.side_effect = mock_responses
        
        article_text = "In response to economic concerns, the Federal Reserve cut interest rates by 0.50 percentage points today."
        result = chat.extract(article_text, self.messages)
        
        self.assertEqual(result, -50)  # Should be negative for decrease
        self.assertEqual(mock_ollama_chat.call_count, 3)
    
    @patch('chat.ollama.chat')
    def test_rate_maintain(self, mock_ollama_chat):
        """Test extraction when rates are maintained at current levels."""
        # Mock responses for the conversation flow
        mock_responses = [
            {'message': {'content': 'Yes'}},  # Initial question response
            {'message': {'content': 'The Federal Reserve decided to maintain current interest rates at their existing levels.'}},  # Sentence extraction
            {'message': {'content': '{"direction": "maintain", "basis_points": 0}'}}  # JSON response
        ]
        mock_ollama_chat.side_effect = mock_responses
        
        article_text = "The Federal Reserve decided to maintain current interest rates at their existing levels, citing stable economic conditions."
        result = chat.extract(article_text, self.messages)
        
        self.assertEqual(result, 0)
        self.assertEqual(mock_ollama_chat.call_count, 3)
    
    @patch('chat.ollama.chat')
    def test_no_fed_decision(self, mock_ollama_chat):
        """Test when there's no Federal Reserve decision about interest rates."""
        # Mock response indicating no FED decision
        mock_responses = [
            {'message': {'content': 'No'}}  # Initial question response - no FED decision
        ]
        mock_ollama_chat.side_effect = mock_responses
        
        article_text = "This is a general economic report discussing market trends and inflation data without any Federal Reserve interest rate decision."
        result = chat.extract(article_text, self.messages)
        
        self.assertIsNone(result)
        self.assertEqual(mock_ollama_chat.call_count, 1)  # Should stop after first response
    
    @patch('chat.ollama.chat')
    def test_json_parsing_error(self, mock_ollama_chat):
        """Test handling of JSON parsing errors."""
        # Mock responses with invalid JSON
        mock_responses = [
            {'message': {'content': 'Yes'}},  # Initial question response
            {'message': {'content': 'The Federal Reserve raised rates by 0.25 percentage points.'}},  # Sentence extraction
            {'message': {'content': 'Invalid JSON response that cannot be parsed'}}  # Invalid JSON
        ]
        mock_ollama_chat.side_effect = mock_responses
        
        article_text = "The Federal Reserve raised rates by 0.25 percentage points."
        result = chat.extract(article_text, self.messages)
        
        self.assertIsNone(result)  # Should return None on parsing error
        self.assertEqual(mock_ollama_chat.call_count, 3)
    
    @patch('chat.ollama.chat')
    def test_empty_article_text(self, mock_ollama_chat):
        """Test handling of empty or None article text."""
        result = chat.extract(None, self.messages)
        self.assertIsNone(result)
        
        result = chat.extract("", self.messages)
        self.assertIsNone(result)
        
        # Should not call ollama.chat for empty input
        mock_ollama_chat.assert_not_called()
    
    @patch('chat.ollama.chat')
    def test_rate_maintain_alternative_phrasing(self, mock_ollama_chat):
        """Test different phrasings for maintaining rates."""
        # Mock responses for the conversation flow
        mock_responses = [
            {'message': {'content': 'Yes'}},  # Initial question response
            {'message': {'content': 'The Committee decided to keep the target range unchanged.'}},  # Sentence extraction
            {'message': {'content': '{"direction": "maintain", "basis_points": 0}'}}  # JSON response
        ]
        mock_ollama_chat.side_effect = mock_responses
        
        article_text = "The FOMC Committee decided to keep the target range for the federal funds rate unchanged at 5.25 to 5.50 percent."
        result = chat.extract(article_text, self.messages)
        
        self.assertEqual(result, 0)
        self.assertEqual(mock_ollama_chat.call_count, 3)

class TestChatWarmup(unittest.TestCase):
    """Unit tests for chat warmup functionality."""
    
    @patch('chat.ollama.chat')
    def test_warmup_returns_messages(self, mock_ollama_chat):
        """Test that warmup returns properly formatted messages."""
        mock_ollama_chat.return_value = {'message': {'content': 'Ready to analyze FOMC statements.'}}
        
        messages = chat.warmup()
        
        self.assertIsInstance(messages, list)
        self.assertEqual(len(messages), 2)  # User prompt + assistant response
        self.assertEqual(messages[0]['role'], 'user')
        self.assertEqual(messages[1]['role'], 'assistant')
        self.assertIn('Federal Reserve decision about interest rates', messages[0]['content'])

if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)