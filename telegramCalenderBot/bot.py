# Written By:Naimuddin Mohammad
# Location : Germany
# Anyone can use it by updating the token and modify as per your choice
# I am not able to provide any support for any query or feature upgrade.

import os
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import calendar
import json
import uuid
from telegram.constants import ParseMode
from telegram.helpers import create_deep_linked_url


class TelegramCalendarBot:
    def __init__(self, token):
        self.token = token
        self.meetings = {}
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle start command and deep linking."""
        if context.args and len(context.args[0]) > 0:
            meeting_id = context.args[0]
            if meeting_id in self.meetings:
                await self.add_to_calendar(update, context, meeting_id)
            else:
                await update.message.reply_text("This meeting invitation is no longer valid.")
            return

        await update.message.reply_text(
            "Welcome to Meeting Organizer Bot!\n"
            "Commands:\n"
            "/schedule - Schedule a new meeting\n"
            "/list - List your meetings\n"
            "/help - Show this help message"
        )

    async def schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start scheduling process."""
        now = datetime.now()
        calendar_markup = self.create_calendar_markup(now.year, now.month)
        await update.message.reply_text(
            "Please select a date:",
            reply_markup=InlineKeyboardMarkup(calendar_markup)
        )

    def create_calendar_markup(self, year, month):
        """Create calendar keyboard."""
        calendar_matrix = calendar.monthcalendar(year, month)
        markup = []
        
        # Month and year header
        header = [InlineKeyboardButton(
            f"{calendar.month_name[month]} {year}",
            callback_data="ignore"
        )]
        markup.append(header)
        
        # Weekday header
        week_days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        markup.append([InlineKeyboardButton(day, callback_data="ignore") for day in week_days])
        
        # Calendar days
        for week in calendar_matrix:
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(" ", callback_data="ignore"))
                else:
                    row.append(InlineKeyboardButton(
                        str(day),
                        callback_data=f"date_{year}_{month}_{day}"
                    ))
            markup.append(row)
            
        return markup

    async def handle_calendar_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle calendar selection."""
        query = update.callback_query
        data = query.data
        
        if data.startswith("date_"):
            _, year, month, day = data.split("_")
            context.user_data['meeting_date'] = {
                'year': int(year),
                'month': int(month),
                'day': int(day)
            }
            await query.message.reply_text(
                "Please enter the meeting time in 24-hour format (HH:MM):"
            )
            context.user_data['expecting_time'] = True
            await query.answer()

    async def create_calendar_event(self, title: str, description: str, start_time: datetime, duration_minutes: int = 60):
        """Create a calendar event message."""
        end_time = start_time + datetime.timedelta(minutes=duration_minutes)
        
        # Format for Telegram's time representation
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp())
        
        # Calculate the time for the 30-minute reminder
        reminder_time = start_time - datetime.timedelta(minutes=30)
        reminder_timestamp = int(reminder_time.timestamp())
        
        # Create calendar event message using Telegram's special format
        calendar_text = (
            f"{title}\n"
            f"📅 <a href='tg://event?startTime={start_timestamp}&"
            f"endTime={end_timestamp}&title={title}&reminderTime={reminder_timestamp}'>{title}</a>\n\n"
            f"📝 {description}\n"
            f"⏰ {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%H:%M')}\n"
            f"🔔 Reminder set for 30 minutes before"
        )
        
        return calendar_text

    async def add_to_calendar(self, update: Update, context: ContextTypes.DEFAULT_TYPE, meeting_id: str):
        """Add meeting to user's Telegram calendar."""
        meeting = self.meetings[meeting_id]
        user_id = update.effective_user.id
        
        if user_id not in meeting['participants']:
            meeting['participants'].append(user_id)
            
            # Create calendar event message
            calendar_text = await self.create_calendar_event(
                title=meeting['title'],
                description=meeting.get('description', 'No description provided'),
                start_time=meeting['datetime']
            )
            
            # Send calendar event message
            keyboard = [[InlineKeyboardButton("Add to Calendar", callback_data=f"add_cal_{meeting_id}")]]
            await update.message.reply_text(
                calendar_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
            
            await update.message.reply_text(
                "You've been added to the meeting!\n"
                "Click 'Add to Calendar' to add it to your Telegram calendar with notifications."
            )
        else:
            await update.message.reply_text("You're already registered for this meeting!")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages for meeting setup."""
        if context.user_data.get('expecting_time'):
            try:
                time = datetime.strptime(update.message.text, "%H:%M").time()
                meeting_date = context.user_data['meeting_date']
                meeting_datetime = datetime(
                    meeting_date['year'],
                    meeting_date['month'],
                    meeting_date['day'],
                    time.hour,
                    time.minute,
                    tzinfo=pytz.UTC
                )
                
                await update.message.reply_text("Please enter the meeting title:")
                context.user_data['meeting_datetime'] = meeting_datetime
                context.user_data['expecting_time'] = False
                context.user_data['expecting_title'] = True
                
            except ValueError:
                await update.message.reply_text(
                    "Invalid time format. Please use HH:MM (e.g., 14:30):"
                )
                
        elif context.user_data.get('expecting_title'):
            meeting_title = update.message.text
            meeting_datetime = context.user_data['meeting_datetime']
            
            # Create meeting ID and store meeting details
            meeting_id = str(uuid.uuid4())[:8]
            self.meetings[meeting_id] = {
                'title': meeting_title,
                'datetime': meeting_datetime,
                'organizer': update.effective_user.id,
                'participants': [update.effective_user.id],
                'description': f"Meeting organized by {update.effective_user.first_name}"
            }
            
            # Create calendar event for organizer
            calendar_text = await self.create_calendar_event(
                title=meeting_title,
                description=self.meetings[meeting_id]['description'],
                start_time=meeting_datetime
            )
            
            # Get bot username for deep linking
            bot_username = (await context.bot.get_me()).username
            invite_link = f"https://t.me/{bot_username}?start={meeting_id}"
            
            # Create invite message with calendar event
            keyboard = [
                [InlineKeyboardButton("Add to Calendar", callback_data=f"add_cal_{meeting_id}")],
                [InlineKeyboardButton("Share Meeting", url=invite_link)]
            ]
            
            await update.message.reply_text(
                f"{calendar_text}\n\n"
                f"Share this link to invite others:\n{invite_link}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
            
            context.user_data.clear()

    async def handle_calendar_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle calendar button clicks."""
        query = update.callback_query
        data = query.data
        
        if data.startswith("add_cal_"):
            meeting_id = data.split("_")[2]
            meeting = self.meetings[meeting_id]
            
            # Create calendar event message with special Telegram format
            calendar_text = await self.create_calendar_event(
                title=meeting['title'],
                description=meeting['description'],
                start_time=meeting['datetime']
            )
            
            # Update the message to show it's been added
            await query.message.edit_text(
                f"{calendar_text}\n\n✅ Added to your calendar!",
                parse_mode=ParseMode.HTML
            )
            
            await query.answer("Meeting added to your calendar!")

    async def list_meetings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List user's meetings."""
        user_id = update.effective_user.id
        user_meetings = [
            (meeting_id, meeting) for meeting_id, meeting in self.meetings.items()
            if user_id in meeting['participants']
        ]
        
        if not user_meetings:
            await update.message.reply_text("You have no scheduled meetings.")
            return
            
        for meeting_id, meeting in user_meetings:
            calendar_text = await self.create_calendar_event(
                title=meeting['title'],
                description=meeting['description'],
                start_time=meeting['datetime']
            )
            
            keyboard = [[InlineKeyboardButton("Add to Calendar", callback_data=f"add_cal_{meeting_id}")]]
            await update.message.reply_text(
                calendar_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )

    def run(self):
        """Run the bot."""
        application = Application.builder().token(self.token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("schedule", self.schedule))
        application.add_handler(CommandHandler("list", self.list_meetings))
        application.add_handler(CallbackQueryHandler(self.handle_calendar_button, pattern="^add_cal_"))
        application.add_handler(CallbackQueryHandler(self.handle_calendar_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Start the bot
        application.run_polling()


# WRITE YOUR TOKEN FROM TELEGRAM

if __name__ == "__main__":
    BOT_TOKEN = "YOUR TOKEN"
    bot = TelegramCalendarBot(BOT_TOKEN)
    bot.run()