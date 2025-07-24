# Story System

**Location:** [`cogs/story/`](cogs/story/)

The Story System is an advanced, interactive, and collaborative storytelling feature. It utilizes a sophisticated multi-agent AI architecture to create dynamic narratives guided by user actions and a "Game Master" AI.

## Core Components

The system is a collection of specialized modules that work in concert:

*   **[Story Manager](./manager.md):** The central orchestrator that directs the entire story generation pipeline.
*   **[Database](./database.md):** Manages the persistent storage of worlds, characters, and the state of ongoing stories.
*   **[Prompt Engine](./prompt_engine.md):** Dynamically constructs complex prompts for the different AI agents.
*   **[State Manager](./state_manager.md):** Updates the story's state (location, time, etc.) based on the AI's decisions.
*   **[UI Manager](./ui_manager.md):** Handles all user-facing Discord UI, such as menus and modals.

## Multi-Agent Architecture

The system's core is its layered AI agent architecture, which separates the roles of planning and acting:

1.  **The Player:** A human user who provides input that influences the story.
2.  **The Director (Game Master) Agent:** An AI whose job is not to write the story, but to *plan* it. It analyzes the current state and the player's input, then generates a structured `GMActionPlan` JSON object. This plan outlines the next event, updates the world state (time, location), and provides high-level instructions (motivation, emotional state) for the characters involved.
3.  **The Actor (Character) Agents:** For each character set to speak or act in the Director's plan, a separate AI agent is invoked. Each Actor agent receives its specific instructions from the Director and generates a `CharacterAction` JSON object containing its dialogue, actions, and internal thoughts.

This separation allows for more coherent and controllable long-form storytelling. The Director maintains the overall plot, while the Actors focus on bringing individual characters to life.