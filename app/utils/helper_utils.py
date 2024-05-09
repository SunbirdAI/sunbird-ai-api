def chunk_text(text, chunk_size=100):
    """
    Split the text into chunks of specified size (default: 100 words).
    """
    words = text.split()
    chunks = [words[i : i + chunk_size] for i in range(0, len(words), chunk_size)]
    return [" ".join(chunk) for chunk in chunks]
