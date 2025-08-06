import os
import openai
from dotenv import load_dotenv

load_dotenv("variables.env") 
openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=openai.api_key)

def chat_with_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def cmd_gptwrite(args, vaults, current_vault, prompt_input, chat_with_gpt):
    if ':' not in args:
        print("Usage: gptwrite NoteName.md: prompt text here")
        return

    note_name, prompt = [a.strip() for a in args.split(':', 1)]
    if not note_name.endswith(".md"):
        note_name += ".md"

    print(f"Sending to ChatGPT: {prompt}")
    response = chat_with_gpt(prompt)

    print("\n--- ChatGPT Response ---\n")
    print(response)
    print("\n------------------------\n")

    confirm = prompt_input(f"Append to {note_name}? (Y/N): ").strip().lower()
    if confirm == 'y':
        note_path = os.path.join(vaults[current_vault], note_name)
        with open(note_path, "a", encoding="utf-8") as f:
            f.write("\n" + response + "\n")
        print(f"Content added to {note_name}.")
    else:
        print("Content not saved.")

def cmd_editnote(args, vaults, current_vault, prompt_input, list_md_files, chat_with_gpt):
    files = list_md_files()
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
        note_file = None
        for f in files:
            if f.lower() == selection.lower():
                note_file = f
                break
        if not note_file:
            print("Note not found.")
            return

    instruction = prompt_input("What do you want ChatGPT to do with this note? (e.g., summarize, fix grammar):\n").strip()
    full_path = os.path.join(vaults[current_vault], note_file)
    with open(full_path, "r", encoding="utf-8") as file:
        content = file.read()

    prompt = f"Here is a note:\n\n{content}\n\nUser asks: {instruction}\n\nPlease respond appropriately."
    try:
        gpt_response = chat_with_gpt(prompt)
    except Exception as e:
        print(f"Error communicating with ChatGPT: {e}")
        return

    print(f"\n--- ChatGPT Response ---\n{gpt_response}\n")
    print("What do you want to do with ChatGPT’s response?")
    print("  [A]ppend to note\n  [O]verwrite note\n  [S]ave as new file\n  [C]ancel")

    choice = prompt_input("Choose (A/O/S/C): ").strip().lower()
    if choice == 'a':
        with open(full_path, "a", encoding="utf-8") as f:
            f.write("\n\n--- ChatGPT Edit ---\n" + gpt_response + "\n")
        print(f"Appended to {note_file}.")
    elif choice == 'o':
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(gpt_response)
        print(f"Overwrote {note_file} with ChatGPT’s response.")
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
