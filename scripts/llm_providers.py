#!/usr/bin/env python3
"""
LLM Provider abstraction with fallback chain for Homunculus.

Supports multiple LLM backends:
- Session: Uses Claude Code session (future)
- Anthropic: Direct API via ANTHROPIC_API_KEY or stored credentials
- Ollama: Local Ollama instance
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Any, Dict

# Optional import for Ollama support
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = None  # type: ignore

import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_config

# Credentials file path
CREDENTIALS_PATH = Path.home() / ".homunculus" / "credentials.json"


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    text: str
    provider: str
    model: str
    tokens_used: Optional[int] = None
    raw_response: Optional[Any] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available/configured."""
        pass

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 4096) -> Optional[LLMResponse]:
        """Generate a response from the LLM."""
        pass

    def get_model_identifier(self) -> str:
        """Get the model identifier for tracking."""
        return f"{self.name}:unknown"


class SessionProvider(LLMProvider):
    """
    Provider that uses Claude Code session (future implementation).
    This would allow synthesis to happen within the current Claude session.
    """

    name = "session"

    def is_available(self) -> bool:
        # Future: check if running within a Claude Code session
        # For now, always return False
        return False

    def generate(self, prompt: str, max_tokens: int = 4096) -> Optional[LLMResponse]:
        # Future: invoke Claude within the current session
        return None

    def get_model_identifier(self) -> str:
        return "session:claude"


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic's Claude API."""

    name = "anthropic"

    def __init__(self):
        self.api_key = self._get_api_key()
        self.model = self._get_model()

    def _get_api_key(self) -> Optional[str]:
        """Get API key from environment or stored credentials."""
        # Check environment first
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if api_key:
            return api_key

        # Check stored credentials
        if CREDENTIALS_PATH.exists():
            try:
                creds = json.loads(CREDENTIALS_PATH.read_text())
                return creds.get('anthropic', {}).get('api_key')
            except (json.JSONDecodeError, IOError):
                pass

        return None

    def _get_model(self) -> str:
        """Get the model to use from config."""
        config = load_config()
        synthesis_config = config.get('synthesis', {})
        model = synthesis_config.get('synthesis_model', 'sonnet')

        # Map config names to API model IDs
        model_map = {
            'sonnet': 'claude-sonnet-4-20250514',
            'haiku': 'claude-3-5-haiku-20241022',
            'opus': 'claude-opus-4-20250514',
        }
        return model_map.get(model, model)

    def is_available(self) -> bool:
        return self.api_key is not None

    def generate(self, prompt: str, max_tokens: int = 4096) -> Optional[LLMResponse]:
        if not self.api_key:
            return None

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)

            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )

            return LLMResponse(
                text=response.content[0].text,
                provider=self.name,
                model=self.model,
                tokens_used=response.usage.output_tokens if response.usage else None,
                raw_response=response
            )
        except ImportError:
            print("Warning: anthropic package not installed")
            return None
        except Exception as e:
            print(f"Anthropic API error: {e}")
            return None

    def get_model_identifier(self) -> str:
        return f"anthropic:{self.model}"


class OllamaProvider(LLMProvider):
    """Provider for local Ollama instance."""

    name = "ollama"

    def __init__(self):
        self.base_url = "http://localhost:11434"
        self.model = self._get_model()

    def _get_model(self) -> str:
        """Get the Ollama model from config."""
        config = load_config()
        synthesis_config = config.get('synthesis', {})
        return synthesis_config.get('ollama_model', 'llama3.2')

    def is_available(self) -> bool:
        """Check if Ollama is running and responsive."""
        if not HAS_REQUESTS:
            return False

        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, max_tokens: int = 4096) -> Optional[LLMResponse]:
        if not HAS_REQUESTS or not self.is_available():
            return None

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens
                    }
                },
                timeout=120
            )

            if response.status_code != 200:
                return None

            data = response.json()
            return LLMResponse(
                text=data.get('response', ''),
                provider=self.name,
                model=self.model,
                tokens_used=data.get('eval_count'),
                raw_response=data
            )
        except Exception as e:
            print(f"Ollama error: {e}")
            return None

    def get_model_identifier(self) -> str:
        return f"ollama:{self.model}"


class LLMProviderChain:
    """
    Chain of LLM providers with fallback support.
    Tries each provider in order until one succeeds.
    """

    def __init__(self, provider_order: Optional[List[str]] = None):
        """
        Initialize the provider chain.

        Args:
            provider_order: List of provider names to try in order.
                           Defaults to ['session', 'anthropic', 'ollama']
        """
        if provider_order is None:
            # Load from config or use default
            config = load_config()
            provider_order = config.get('synthesis', {}).get(
                'provider_order',
                ['session', 'anthropic', 'ollama']
            )

        self.provider_order = provider_order
        self.providers: Dict[str, LLMProvider] = {
            'session': SessionProvider(),
            'anthropic': AnthropicProvider(),
            'ollama': OllamaProvider(),
        }

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names."""
        available = []
        for name in self.provider_order:
            provider = self.providers.get(name)
            if provider and provider.is_available():
                available.append(name)
        return available

    def generate(self, prompt: str, max_tokens: int = 4096) -> Optional[LLMResponse]:
        """
        Generate a response using the first available provider.

        Args:
            prompt: The prompt to send to the LLM
            max_tokens: Maximum tokens in response

        Returns:
            LLMResponse if successful, None if all providers fail
        """
        for provider_name in self.provider_order:
            provider = self.providers.get(provider_name)
            if not provider:
                continue

            if not provider.is_available():
                continue

            response = provider.generate(prompt, max_tokens)
            if response:
                return response

        return None

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status information for all providers."""
        status = {}
        for name, provider in self.providers.items():
            available = provider.is_available()
            status[name] = {
                'available': available,
                'model': provider.get_model_identifier() if available else None,
                'in_chain': name in self.provider_order
            }
        return status


# Convenience functions for backward compatibility
def get_llm_client() -> Optional[Any]:
    """
    Get an LLM client (backward compatible).
    Returns the Anthropic client if available.
    """
    provider = AnthropicProvider()
    if provider.is_available() and provider.api_key:
        try:
            import anthropic
            return anthropic.Anthropic(api_key=provider.api_key)
        except ImportError:
            pass
    return None


def get_provider_chain() -> LLMProviderChain:
    """Get a configured LLM provider chain."""
    return LLMProviderChain()


# Credential management
def store_anthropic_key(api_key: str) -> bool:
    """
    Store Anthropic API key securely.

    Args:
        api_key: The API key to store

    Returns:
        True if stored successfully
    """
    try:
        CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Load existing credentials
        creds = {}
        if CREDENTIALS_PATH.exists():
            try:
                creds = json.loads(CREDENTIALS_PATH.read_text())
            except (json.JSONDecodeError, IOError):
                pass

        # Update with new key
        creds['anthropic'] = {'api_key': api_key}

        # Write with restricted permissions
        CREDENTIALS_PATH.write_text(json.dumps(creds, indent=2))
        os.chmod(CREDENTIALS_PATH, 0o600)

        return True
    except Exception as e:
        print(f"Error storing credentials: {e}")
        return False


def clear_anthropic_key() -> bool:
    """Remove stored Anthropic API key."""
    try:
        if not CREDENTIALS_PATH.exists():
            return True

        creds = json.loads(CREDENTIALS_PATH.read_text())
        if 'anthropic' in creds:
            del creds['anthropic']
            CREDENTIALS_PATH.write_text(json.dumps(creds, indent=2))

        return True
    except Exception as e:
        print(f"Error clearing credentials: {e}")
        return False


if __name__ == "__main__":
    # Test the provider chain
    print("LLM Provider Status:")
    print("-" * 40)

    chain = LLMProviderChain()
    status = chain.get_provider_status()

    for name, info in status.items():
        available = "Yes" if info['available'] else "No"
        model = info['model'] or "N/A"
        in_chain = "Yes" if info['in_chain'] else "No"
        print(f"  {name}: available={available}, model={model}, in_chain={in_chain}")

    print()
    print("Available providers:", chain.get_available_providers())
