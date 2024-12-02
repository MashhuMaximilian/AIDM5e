## 1. Very Short Description

**AIDM** is a versatile Discord bot designed for Dungeon Masters and role-playing enthusiasts. It enhances campaign management with AI-powered features like channel and thread memory assignments, dynamic NPC and lore tracking, combat status updates, and seamless collaboration through message summaries and cross-channel communication. AIDM ensures immersive gameplay by providing quick 5e rule lookups, character management, and creative assistance for campaigns or one-shots—all in a customizable and user-friendly interface.

---

## 2. How to Install

2.1. **Clone the Repository**  
   ```bash
   git clone https://github.com/MashhuMaximilian/AIDM5e
   cd aidm5e
   ```

2.2. **Set Up Dependencies**  
   Install the required Python packages:  
   ```bash
   pip install -r requirements.txt
   ```

2.3. **Set Up Your Bot**  
   - Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).  
   - Obtain the bot token.  

2.4. **Configure the Project**  
   - create .env file and add your tokens: OPENAI_API_KEY (OpenAI project API key), DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, ASSISTANT_ID (your openAI assistant you want to use) 

2.5. **Run the Bot**  
   ```bash
   python3 aidm.py
   ```  
   AIDM should now be online in your Discord server!

---
## 3. Contribution Guidelines

We’re thrilled that you’re considering contributing to AIDM! Whether it’s fixing bugs, suggesting features, or enhancing documentation, your help is greatly appreciated. Here’s how you can get started:

3.1. **Fork and Clone**  
   First, fork the repository and clone it to your local machine:  
   ```bash
   git clone https://github.com/yourusername/aidm.git
   cd aidm
   ```

3.2. **Create a Branch**  
   Make a new branch for your changes:  
   ```bash
   git checkout -b your-feature-name
   ```

3.3. **Make Your Changes**  
   - Improve the code, add a feature, or update the documentation.  
   - Try to keep your changes focused and well-documented.  

3.4. **Test Your Work**  
   Ensure everything works smoothly, and nothing breaks unexpectedly. If you’ve added a feature, check it thoroughly.

3.5. **Commit and Push**  
   Commit your changes with a meaningful message and push them to your fork:  
   ```bash
   git add .
   git commit -m "Describe what you’ve done"
   git push origin your-feature-name
   ```

3.6. **Open a Pull Request**  
   Head back to the original repository and open a pull request. Explain what your contribution does and why it’s useful.

## Tips for Contributors
- Keep changes small and focused.  
- Be kind and collaborative—this is a community project.  
- Don’t hesitate to ask questions or start discussions in issues if you’re stuck.

Thanks for helping make AIDM even better!


Let’s create a comprehensive **Intro** and **Features** section that fully incorporates all the practical use cases, tips, and features we've discussed, while keeping it human and relatable.  

---
# More about AIDM 5e — Tips and How to

### Intro  

AIDM (AI Dungeon Master) is a game-changing tool for tabletop RPG players and GMs, fully integrated with Discord. Whether you're running a sprawling campaign, managing character stats, or brainstorming creative ideas, AIDM adapts to your needs.  

It’s more than just an assistant—it’s your go-to partner for enhancing organization, creativity, and immersion in any RPG setting. AIDM helps with world-building, combat management, player feedback, and more—all while keeping your campaign notes tidy and accessible. From managing multiple campaigns to creating vivid characters, AIDM makes every session seamless and engaging.  

---

### Features  

#### **How to Use AIDM in Your Campaigns**  
- **Campaign Management:** Create a separate Discord category for each campaign or one-shot.
- Upon using `/invite`, the following channels will be created:  
  - `#gameplay`: The heart of the campaign, where the story unfolds. (Memory: `gameplay`)
  - `#feedback`: For player insights and critiques, tied to the same memory as `#gameplay` (Memory: `gameplay`).  
  - `#telldm`: Ask the DM private questions or raise issues mid-game (Memory: `out-of-game`).  
  - `#session-summary`: Automatically summarize key moments and events (Memory: `out-of-game`).  

- **Create Memories for Everything:**  
  - Assign memories to channels or threads to keep lore, character info, and campaign events organized.  
  - Use the default in-game memory for tracking the main story and the out-of-game memory for rules, meta discussions, and campaign-wide status. 
  - Set up custom memories for individual characters, NPCs, or combat encounters. 

- **Combat Management:**
- Create a separate thread in the `#gameplay` channel for combat. Use the same memory for continuity or assign a dedicated combat memory. The choice is yours. Flexibility is the name of the game.
	- Afterward, in case you have 2 separate memories for main gameplay and combat, you summarize the key points of the combat and send the recap to the `#gameplay` memory for a clean recap.  

- **World-Building and Creativity:**  
  - Use AIDM to brainstorm lore, build worlds, or plan new campaigns.
  - Use AIDM to create a new character or help you with improving your existing character (like when choosing new things for a level up)
  - Share PDFs, images, and docs directly in Discord for collaborative storytelling (these can include character sheets, encounter maps, etc.).  

- **Summarization and Messaging:**  
  - Use `/summarize` to quickly recap a session or catch up on a thread.  
  - Send updates across memories and channels with the `/send` command, ensuring everyone stays informed.  

#### **Practical Tips for Organizing Your Game**  
- **Keep Feedback Separate:** Use the same memory for `#feedback` and `#gameplay` but keep the channels distinct for better organization.  
- **Always-On Mode:** Automate AIDM responses to every message or limit them to mentions for better control.  
- **Character-Specific Threads:** Create threads in `#characters` to manage AC, HP, spell slots, and other stats.  
- **Lore and Notes:** Use AIDM’s `#telldm #for campaign-related knowledge` and `/askdm #for general knowledge)` commands to inquire about world-building notes, NPC details, items, or general 5e rules.

#### **Audio Summaries:**
- AIDM can join a voice channel to capture your session's audio.
Once the session ends, the bot sends a text summary of key moments to the #session-summary channel.

#### **Key Features**  
1. **Custom Memories:** Assign unique memories for gameplay, characters, world-building, and more.  
2. **Thread and Channel Integration:** Manage combat, characters, or special events in focused threads or channels.  
3. **Summarization:** Recap channel discussions or game sessions in seconds.  
4. **Cross-Memory Communication:** Send messages between threads, channels, or memories for seamless gameplay updates.  
5. **Rich Media Support:** Share images, PDFs, and other files for enhanced storytelling.  
6. **Dynamic Automation:** Set up “Always-On” mode to let AIDM respond automatically or restrict interactions to mentions.  
7. **Collaborative Tools:** Plan campaigns, brainstorm ideas, and create vivid characters with ease.
8. **Audio Summaries:** Automatically convert session recordings into text and store them in #session-summary.

---  

### 6) Command Overview  

Here's a breakdown of all the commands, their parameters, and what they do:  

---

#### **`/startnew`**  
Create a new channel, thread, or memory for organizing your campaign.  
- **`channel:`** Select an existing channel in the category or create a new one.  
- **`always_on:`** Toggle whether the bot responds to all messages (`ON`) or only mentions (`OFF`).  
- **`memory:`** Assign an existing memory or create a new one.  
- **`memory_name:`** Name the memory to be created (required if `CREATE NEW MEMORY` is selected).  
- **`channel_name:`** Name for the new channel (required if `NEW CHANNEL` is selected).  
- **`thread_name:`** Name for the new thread (required if `NEW THREAD` is selected).  
- **`thread:`** Select an existing thread in the channel or create a new one.  

**Examples:**  
- `/startnew channel: NEW CHANNEL channel_name: gameplay always_on: ON memory: gameplay`  
  Creates a new channel called `gameplay` with the `gameplay` memory.  
- `/startnew channel: characters thread: NEW THREAD thread_name: Alice memory: CREATE NEW MEMORY memory_name: Alice Memory`  
  Creates a thread called `Alice` in the `characters` channel with a new memory named `Alice Memory`.  

---

#### **`/assign_memory`**  
Assign a memory to a channel or thread.  
- **`channel:`** Choose the channel to assign memory.  
- **`memory:`** Select an existing memory or create a new one.  
- **`memory_name:`** Name for the memory to be created (if `CREATE NEW MEMORY` is selected).  
- **`thread:`** (Optional) Assign the memory to a thread within the channel.  
- **`always_on:`** (Optional) Set `ON` or `OFF` for the memory in this context.  

**Examples:**  
- `/assign_memory channel: gameplay memory: CREATE NEW MEMORY memory_name: Battle Memory`  
  Creates and assigns a memory named `Battle Memory` to the `gameplay` channel.  
- `/assign_memory channel: characters memory: Alice Memory thread: Alice`  
  Assigns the `Alice Memory` to the `Alice` thread in the `characters` channel.  

---

#### **`/send`**  
Send a message to another channel or thread while specifying the memory to use.  
- **`channel:`** Target channel to send the message.  
- **`message:`** The message to send.  
- **`memory:`** Specify the memory to use when sending the message.  

**Example:**  
- `/send channel: feedback memory: gameplay message: "Check out the updated spell list!"`  

---

#### **`/summarize`**  
Get a summary of recent messages from a channel or thread.  
- **`channel:`** The channel to summarize.  
- **`thread:`** (Optional) A specific thread to summarize.  

**Example:**  
- `/summarize channel: gameplay`  
  Provides a summary of the recent gameplay session.  

---

#### **`/set_always_on`**  
Toggle whether the bot responds to all messages or only mentions in a specific channel or thread.  
- **`channel:`** Target channel to modify.  
- **`thread:`** (Optional) Target thread within the channel.  
- **`always_on:`** Set to `ON` or `OFF`.  

**Example:**  
- `/set_always_on channel: feedback always_on: ON`  

---

#### **`/askdm`**  
Query the bot about general 5e rules, spells, monsters, items, or mechanics.  
- **`query:`** Your general DND question. The answer will include item/spell/race features and descriptions as well as official sources. You will choose from an options list whether your question is about a spell, an item, a race or class, a monster, etc. The answer will be sent to `#telldm` or you can choose in which other channel or thread you want the answer.  

**Example:**  
- `/askdm query: "What are the rules for concentration spells?"`
- `/askdm query: "Fireball"`

---

#### **`/tellme`**  
Ask the bot about campaign-specific lore, items, players, or NPCs.  
- **`query:`** Your question. You will choose from an options list whether your question is about inventory, a specific location or NPC, or other campaign-related knowledge. The answer will be sent to `#telldm` or you can choose in which other channel or thread you want the answer.  

**Example:**  
- `/tellme query: "What did Dzargo tell us about Verinia's siege?"`  

---

#### **`/invite`**  
Initialize threads and channels for a category and creates the channels: `#gameplay`, `#feedback`, `#session-summary`, `#telldm`.  

---

#### **`/delete_memory`**  
Delete a specific memory from the category.  
- **`memory_name:`** The name of the memory to delete.

---

#### **`/feedback`**  
Offer feedback to AIDM.  
- **`suggestions:`** The feedback you want to give.
- `/feedback suggestions: "Please describe the encounter more lively from now on. It needs to be more catchy and visual."`
---

### 7) License  

This project is licensed under the **GNU General Public License v3.0**.  

**You are free to:**  
- Use the software for any purpose.  
- Distribute the software.  
- Modify the software.  
- Distribute modified versions.  

**Under the following terms:**  
- You must disclose the source of your modifications.  
- You cannot hold the authors liable.  

For the full license text, see the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html).  

---  
