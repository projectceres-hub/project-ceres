"""
GPT integration module for Project Ceres.

Provides functions for interacting with OpenAI's GPT API.
"""

import os
import openai
from pathlib import Path
from typing import Optional, Callable, Dict


class GPTClient:
    """
    OpenAI GPT client wrapper.
    
    Encapsulates the OpenAI client to avoid global state.
    """
    
    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4o") -> None:
        """
        Initialize GPT client.
        
        Args:
            api_key: OpenAI API key. If None, must be provided via Config.
            default_model: Default model to use for chat requests.
            
        Raises:
            ValueError: If API key is not provided
            openai.OpenAIError: If client initialization fails
        """
        if api_key is None:
            raise ValueError("API key must be provided")
        
        try:
            self.client = openai.OpenAI(api_key=api_key)
            self.default_model = default_model
        except Exception as e:
            print(f"Error: Failed to initialize OpenAI client: {e}")
            print("Hint: Check that your API key is valid and you have an internet connection.")
            raise
    
    def chat(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Send a chat prompt to GPT and return the response.
        
        Args:
            prompt: The user's prompt
            model: The model to use. If None, uses default_model.
            
        Returns:
            The GPT response content
            
        Raises:
            openai.APIError: If API request fails
            openai.RateLimitError: If rate limit is exceeded
            openai.APIConnectionError: If connection fails
        """
        if model is None:
            model = self.default_model
        
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except openai.RateLimitError as e:
            print(f"Error: OpenAI API rate limit exceeded: {e}")
            print("Hint: Wait a moment and try again, or check your API usage limits.")
            raise
        except openai.APIConnectionError as e:
            print(f"Error: Failed to connect to OpenAI API: {e}")
            print("Hint: Check your internet connection and try again.")
            raise
        except openai.APIError as e:
            print(f"Error: OpenAI API request failed: {e}")
            print("Hint: Check your API key is valid and you have sufficient credits.")
            raise
        except Exception as e:
            print(f"Error: Unexpected error communicating with OpenAI: {e}")
            print("Hint: Check your API key and network connection.")
            raise


def create_gpt_client(api_key: Optional[str] = None, default_model: str = "gpt-4o") -> GPTClient:
    """
    Factory function to create a GPT client.
    
    Args:
        api_key: OpenAI API key. If None, must be provided via Config.
        default_model: Default model to use (default: "gpt-4o").
        
    Returns:
        Initialized GPTClient instance
    """
    return GPTClient(api_key=api_key, default_model=default_model)


def chat_with_gpt(
    prompt: str,
    client: Optional[GPTClient] = None,
    api_key: Optional[str] = None,
    default_model: str = "gpt-4o"
) -> str:
    """
    Convenience function for chat_with_gpt compatibility.
    
    Args:
        prompt: The user's prompt
        client: GPTClient instance. If None, creates a new one.
        api_key: API key to use if creating new client (optional).
        default_model: Default model to use if creating new client.
        
    Returns:
        The GPT response content
    """
    if client is None:
        client = create_gpt_client(api_key=api_key, default_model=default_model)
    return client.chat(prompt)

def cmd_gptwrite(
    args: str,
    vaults: Dict[str, str],
    current_vault: str,
    prompt_input: Callable[[str], str],
    gpt_client: GPTClient,
    history_manager
) -> None:
    """
    Write content to a note using GPT.
    
    Args:
        args: Command arguments in format "NoteName.md: prompt text"
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        prompt_input: Function to get user input
        gpt_client: GPT client instance
    """
    if ':' not in args:
        print("Usage: gptwrite NoteName.md: prompt text here")
        return

    note_name, prompt = [a.strip() for a in args.split(':', 1)]
    if not note_name.endswith(".md"):
        note_name += ".md"

    print(f"Sending to ChatGPT: {prompt}")
    try:
        response = gpt_client.chat(prompt)
    except Exception as e:
        print(f"Error: Failed to get response from ChatGPT: {e}")
        return

    print("\n--- ChatGPT Response ---\n")
    print(response)
    print("\n------------------------\n")

    confirm = prompt_input(f"Append to {note_name}? (Y/N): ").strip().lower()
    if confirm == 'y':
        note_path = Path(vaults[current_vault]) / note_name
        try:
            # Backup before appending
            history_manager.backup_note(note_path)
            with open(note_path, "a", encoding="utf-8") as f:
                f.write("\n" + response + "\n")
            print(f"Content added to {note_name}.")
        except OSError as e:
            print(f"Error: Failed to write to note file '{note_name}': {e}")
            print(f"Hint: Check that the vault path '{vaults[current_vault]}' exists and is writable.")
        except Exception as e:
            print(f"Error: Unexpected error writing to file: {e}")
            print(f"Hint: Check file permissions and disk space.")
    else:
        print("Content not saved.")

def cmd_editnote(
    args: str,
    vaults: Dict[str, str],
    current_vault: str,
    prompt_input: Callable[[str], str],
    list_md_files: Callable,
    read_md_file: Callable,
    gpt_client: GPTClient,
    history_manager
) -> None:
    """
    Edit a note using GPT.
    
    Allows user to select a note and have GPT modify it based on instructions.
    User can choose to append, overwrite, or save as new file.
    
    Args:
        args: Command arguments (unused)
        vaults: Dictionary mapping vault names to paths
        current_vault: Name of the current active vault
        prompt_input: Function to get user input
        list_md_files: Function to list markdown files in vault
        read_md_file: Function to read markdown file content
        gpt_client: GPT client instance
    """
    files = list_md_files(vaults, current_vault, lambda *_: None)
    if not files:
        print("No markdown files in the current vault.")
        return

    print("Notes in current vault:")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")

    selection = prompt_input("Enter the number or name of the note to edit: ").strip()
    try:
        idx = int(selection) - 1
        if 0 <= idx < len(files):
            note_file = files[idx]
        else:
            print("Invalid selection.")
            return
    except ValueError:
        note_file = next((f for f in files if f.lower() == selection.lower()), None)
        if not note_file:
            print("Note not found.")
            return

    instruction = prompt_input("What do you want ChatGPT to do with this note? (e.g., summarize, fix grammar):\n").strip()
    content = read_md_file(note_file, vaults, current_vault, lambda *_: None)
    prompt = f"Here is a note:\n\n{content}\n\nUser asks: {instruction}\n\nPlease respond appropriately."

    try:
        gpt_response = gpt_client.chat(prompt)
    except Exception as e:
        print(f"Error communicating with ChatGPT: {e}")
        return

    print(f"\n--- ChatGPT Response ---\n{gpt_response}\n")
    print("What do you want to do with ChatGPT’s response?")
    print("  [A]ppend to note\n  [O]verwrite note\n  [S]ave as new file\n  [C]ancel")

    choice = prompt_input("Choose (A/O/S/C): ").strip().lower()
    full_path = Path(vaults[current_vault]) / note_file
    try:
        if choice == 'a':
            # Backup before appending
            history_manager.backup_note(full_path)
            with open(full_path, "a", encoding="utf-8") as f:
                f.write("\n\n--- ChatGPT Edit ---\n" + gpt_response + "\n")
            print(f"Appended to {note_file}.")
        elif choice == 'o':
            # Backup before overwriting
            history_manager.backup_note(full_path)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(gpt_response)
            print(f"Overwrote {note_file} with ChatGPT's response.")
        elif choice == 's':
            new_name = prompt_input("Enter new note name (with or without .md): ").strip()
            if not new_name.endswith(".md"):
                new_name += ".md"
            new_path = os.path.join(vaults[current_vault], new_name)
            with open(new_path, "w", encoding="utf-8") as f:
                f.write(gpt_response)
            print(f"Saved as new note: {new_name}")
        else:
            print("Canceled. No changes made.")
    except OSError as e:
        print(f"Error: Failed to write to note file: {e}")
        print(f"Hint: Check that the vault path '{vaults[current_vault]}' exists and is writable.")
    except Exception as e:
        print(f"Error: Unexpected error writing file: {e}")
        print("Hint: Check file permissions and disk space.")

