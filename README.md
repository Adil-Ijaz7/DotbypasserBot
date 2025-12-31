# DotbypasserBot

A Telegram bot for bypassing dot restrictions.

## Deployment on GitHub Actions

This bot can be deployed to run automatically on GitHub Actions.

### Setting up the BOT_TOKEN Secret

1. Go to your GitHub repository settings
2. Navigate to **Settings** > **Secrets and variables** > **Actions**
3. Click on **New repository secret**
4. Name: `BOT_TOKEN`
5. Value: Your Telegram bot token (e.g., `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)
6. Click **Add secret**

### Running the Bot

The bot will automatically run:
- On every push to the `main` branch
- Every 6 hours via scheduled cron job
- Manually via the **Actions** tab > **Run Telegram Bot** > **Run workflow**

### Manual Trigger

1. Go to the **Actions** tab in your repository
2. Select **Run Telegram Bot** workflow
3. Click **Run workflow** button
4. Select the branch (usually `main`)
5. Click **Run workflow**

### Important Limitations

⚠️ **GitHub Actions Limitations for 24/7 Bots:**
- GitHub Actions has a maximum runtime of 6 hours per job
- The bot will restart every 6 hours (via cron schedule)
- There may be brief downtime between restarts
- For true 24/7 operation, consider deploying to a dedicated server or cloud platform (e.g., Heroku, Railway, AWS, etc.)

### Local Development

To run the bot locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variable
export BOT_TOKEN="your_bot_token_here"

# Run the bot
python main.py
```
