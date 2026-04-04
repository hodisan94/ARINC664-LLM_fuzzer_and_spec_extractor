"""
Multi-provider LLM client supporting OpenAI (GPT), Anthropic (Claude),
Google (Gemini), and Mistral.

This module extends the existing llm_client.py to support multiple LLM providers
for cross-model validation of protocol rule extraction.

Required environment variables:
- OPENAI_API_KEY: For GPT models
- ANTHROPIC_API_KEY: For Claude models  
- MISTRAL_API_KEY: For Mistral models
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum


class ModelProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MISTRAL = "mistral"


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, model: str, api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key
    
    @abstractmethod
    def query(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str:
        """Send a query and get text response."""
        pass
    
    def query_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Query and parse response as JSON."""
        response = self.query(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Strip markdown code block wrappers (Claude often adds these)
        import re
        stripped = response.strip()
        stripped = re.sub(r'^```(?:json)?\s*\n?', '', stripped)
        stripped = re.sub(r'\n?```\s*$', '', stripped)
        stripped = stripped.strip()
        
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            # Fallback: find the outermost { ... } in the original response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            print(f"Failed to parse JSON from response: {response[:500]}...")
            raise


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider."""
    
    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None):
        super().__init__(model, api_key)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key)
    
    def query(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content.strip()
    
    def query_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """OpenAI supports native JSON mode."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content.strip())


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""
    
    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: Optional[str] = None):
        super().__init__(model, api_key)
        # Support both ANTHROPIC_API_KEY and CLAUDE_API_KEY
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY or CLAUDE_API_KEY environment variable not set")
        
        import anthropic
        self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def query(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        return response.content[0].text.strip()


class MistralProvider(BaseLLMProvider):
    """Mistral provider using OpenAI-compatible API."""
    
    def __init__(self, model: str = "mistral-large-latest", api_key: Optional[str] = None):
        super().__init__(model, api_key)
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY environment variable not set")
        
        from openai import OpenAI
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.mistral.ai/v1"
        )
    
    def query(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content.strip()
    
    def query_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Mistral supports JSON mode via response_format."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content.strip())


class MultiModelClient:
    """
    Client that manages multiple LLM providers for cross-validation.
    
    Usage:
        client = MultiModelClient()
        results = client.query_all(system_prompt, user_prompt)
        # results = {"openai": "...", "anthropic": "...", "google": "..."}
    """
    
    # Default models for each provider
    DEFAULT_MODELS = {
        ModelProvider.OPENAI: "gpt-4o",
        ModelProvider.ANTHROPIC: "claude-sonnet-4-20250514",
        ModelProvider.MISTRAL: "mistral-large-latest"
    }
    
    def __init__(
        self,
        providers: Optional[List[ModelProvider]] = None,
        models: Optional[Dict[ModelProvider, str]] = None
    ):
        """
        Initialize multi-model client.
        
        Args:
            providers: List of providers to use (default: all available)
            models: Custom model names per provider
        """
        self.providers: Dict[ModelProvider, BaseLLMProvider] = {}
        self.models = models or {}
        
        target_providers = providers or list(ModelProvider)
        
        for provider in target_providers:
            try:
                model = self.models.get(provider, self.DEFAULT_MODELS[provider])
                self.providers[provider] = self._create_provider(provider, model)
                print(f"✓ Initialized {provider.value} with model {model}")
            except ValueError as e:
                print(f"✗ Skipping {provider.value}: {e}")
            except ImportError as e:
                print(f"✗ Skipping {provider.value}: missing library - {e}")
    
    def _create_provider(self, provider: ModelProvider, model: str) -> BaseLLMProvider:
        """Create provider instance."""
        if provider == ModelProvider.OPENAI:
            return OpenAIProvider(model=model)
        elif provider == ModelProvider.ANTHROPIC:
            return AnthropicProvider(model=model)
        elif provider == ModelProvider.MISTRAL:
            return MistralProvider(model=model)
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def get_available_providers(self) -> List[ModelProvider]:
        """Get list of successfully initialized providers."""
        return list(self.providers.keys())
    
    def query(
        self,
        provider: ModelProvider,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str:
        """Query a specific provider."""
        if provider not in self.providers:
            raise ValueError(f"Provider {provider.value} not available")
        
        return self.providers[provider].query(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def query_json(
        self,
        provider: ModelProvider,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Query a specific provider and get JSON response."""
        if provider not in self.providers:
            raise ValueError(f"Provider {provider.value} not available")
        
        return self.providers[provider].query_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def query_all(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        as_json: bool = False
    ) -> Dict[str, Any]:
        """
        Query all available providers and return results.
        
        Returns:
            Dictionary with provider names as keys and responses as values.
            If as_json=True, responses are parsed as JSON.
        """
        results = {}
        
        for provider, client in self.providers.items():
            try:
                if as_json:
                    response = client.query_json(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                else:
                    response = client.query(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                results[provider.value] = response
                print(f"  ✓ {provider.value} responded")
            except Exception as e:
                print(f"  ✗ {provider.value} failed: {e}")
                results[provider.value] = {"error": str(e)}
        
        return results


def get_single_provider(provider_name: str) -> BaseLLMProvider:
    """
    Get a single LLM provider by name.
    
    Args:
        provider_name: One of 'openai', 'anthropic', 'google'
    
    Returns:
        Configured LLM provider
    """
    provider = ModelProvider(provider_name)
    client = MultiModelClient(providers=[provider])
    
    if provider not in client.providers:
        raise ValueError(f"Could not initialize {provider_name} provider")
    
    return client.providers[provider]


if __name__ == "__main__":
    # Test the multi-model client
    print("Testing Multi-Model LLM Client")
    print("=" * 50)
    
    client = MultiModelClient()
    
    print(f"\nAvailable providers: {[p.value for p in client.get_available_providers()]}")
    
    if client.get_available_providers():
        print("\nTesting simple query...")
        results = client.query_all(
            system_prompt="You are a helpful assistant.",
            user_prompt="Say 'Hello from [model name]!' and nothing else.",
            temperature=0.3,
            max_tokens=50
        )
        
        print("\nResults:")
        for provider, response in results.items():
            print(f"  {provider}: {response}")

