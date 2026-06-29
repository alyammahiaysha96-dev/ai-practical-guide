#!/usr/bin/env python3

import datetime
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT = Path.home() / "ai-practical-guide" / "website"
TOPICS = PROJECT / "automation" / "topics.txt"
POSTS = PROJECT / "content" / "posts"
LOG = PROJECT / "automation" / "publisher.log"
LOCK = PROJECT / "automation" / ".publisher.lock"

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "gemma3:4b"


def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)

    with LOG.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def run(command):
    result = subprocess.run(
        command,
        cwd=PROJECT,
        text=True,
        capture_output=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n"
            f"{result.stdout}\n{result.stderr}"
        )

    return result.stdout.strip()


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:90]


def load_topics():
    if not TOPICS.exists():
        raise RuntimeError("automation/topics.txt was not found.")

    topics = [
        line.strip()
        for line in TOPICS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if not topics:
        raise RuntimeError("No topics remain in topics.txt.")

    return topics


def generate_article(topic):
    prompt = f"""
Write a useful, original English article about:

{topic}

Target audience:
International English-speaking beginners, including readers in the
United States, United Kingdom, Canada, Australia, and Europe.

Requirements:
- Write between 1,000 and 1,500 words.
- Use clear, natural, professional English.
- Start directly with an introduction.
- Use Markdown headings beginning with ##.
- Include practical steps and examples.
- Include a section called "Common Mistakes to Avoid".
- Include a section called "Privacy and Safety Considerations".
- Finish with a section called "Final Thoughts".
- Do not invent statistics, studies, quotations, prices, or test results.
- Do not claim that a product was personally tested.
- Do not include a title or YAML front matter.
- Do not include affiliate links.
- Do not mention being an AI.
- Avoid repetitive filler.
"""

    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.55,
            "num_predict": 3200
        }
    }).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=1200) as response:
        data = json.loads(response.read().decode("utf-8"))

    article = data.get("response", "").strip()
    word_count = len(article.split())

    if word_count < 750:
        raise RuntimeError(
            f"Generated article was rejected because it only has "
            f"{word_count} words."
        )

    forbidden_phrases = [
        "as an ai language model",
        "i cannot browse",
        "i don't have access to"
    ]

    lowercase_article = article.lower()

    for phrase in forbidden_phrases:
        if phrase in lowercase_article:
            raise RuntimeError(
                f"Generated article contains a forbidden phrase: {phrase}"
            )

    return article


def create_post(topic, article):
    POSTS.mkdir(parents=True, exist_ok=True)

    date = datetime.date.today().isoformat()
    slug = slugify(topic)
    post_path = POSTS / f"{date}-{slug}.md"

    if post_path.exists():
        raise RuntimeError(f"Post already exists: {post_path.name}")

    safe_title = topic.replace('"', "'")
    description = (
        f"A practical beginner-friendly guide to {topic.lower()}, "
        "including useful steps, examples, and safety considerations."
    ).replace('"', "'")

    content = f"""---
title: "{safe_title}"
date: {date}
draft: false
description: "{description}"
tags:
  - artificial intelligence
  - automation
  - productivity
categories:
  - AI Guides
---

{article}
"""

    post_path.write_text(content, encoding="utf-8")
    return post_path


def update_topic_queue(topics):
    remaining = topics[1:]
    text = "\n".join(remaining)

    if text:
        text += "\n"

    TOPICS.write_text(text, encoding="utf-8")


def publish(post_path, topic):
    run(["/opt/homebrew/bin/hugo", "--gc", "--minify"])

    run([
        "/opt/homebrew/bin/git",
        "add",
        str(post_path),
        str(TOPICS)
    ])

    status = subprocess.run(
        ["/opt/homebrew/bin/git", "diff", "--cached", "--quiet"],
        cwd=PROJECT
    )

    if status.returncode == 0:
        raise RuntimeError("No new changes were staged.")

    run([
        "/opt/homebrew/bin/git",
        "commit",
        "-m",
        f"Publish article: {topic}"
    ])

    run([
        "/opt/homebrew/bin/git",
        "push",
        "origin",
        "main"
    ])


def main():
    if LOCK.exists():
        log("Another publisher process appears to be running.")
        sys.exit(1)

    try:
        LOCK.write_text(str(datetime.datetime.now()), encoding="utf-8")

        topics = load_topics()
        topic = topics[0]

        log(f"Selected topic: {topic}")
        article = generate_article(topic)
        log(f"Generated article with {len(article.split())} words.")

        post_path = create_post(topic, article)
        log(f"Created: {post_path.name}")

        update_topic_queue(topics)
        publish(post_path, topic)

        log("Article pushed successfully. GitHub deployment has started.")

    except Exception as error:
        log(f"ERROR: {error}")
        sys.exit(1)

    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
