import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pytz
import threading
import time
import json
import calendar

# Configure your tokens and credentials
TELEGRAM_BOT_TOKEN = '7790327699:AAHNYT10vHbNkYLy2u17k-XrPm36C4RhC2w'
GOOGLE_CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = 'credentials.json'

# Initialize the bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Store temporary event data
user_events = {}
user_states = {}

class CalendarUI:
    def __init__(self):
        self.months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        self.current_shown_dates = {}
    
    def create_calendar(self, year, month):
        markup = InlineKeyboardMarkup()
        
        # First row - Month and Year
        row = [
            InlineKeyboardButton(
                "◀️",
                callback_data=f"previous-month_{year}_{month}"
            ),
            InlineKeyboardButton(
                f"{self.months[month-1]} {year}",
                callback_data="ignore"
            ),
            InlineKeyboardButton(
                "▶️",
                callback_data=f"next-month_{year}_{month}"
            ),
        ]
        markup.row(*row)
        
        # Second row - Days of week
        week_days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        row = [InlineKeyboardButton(day, callback_data="ignore") for day in week_days]
        markup.row(*row)
        
        # Calendar days
        month_calendar = calendar.monthcalendar(year, month)
        for week in month_calendar:
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(" ", callback_data="ignore"))
                else:
                    row.append(InlineKeyboardButton(
                        str(day),
                        callback_data=f"select-day_{year}_{month}_{day}"
                    ))
            markup.row(*row)
            
        return markup

    def create_time_selector(self, selected_date):
        markup = InlineKeyboardMarkup(row_width=4)
        hours = []
        
        # Create 24-hour selection buttons
        for hour in range(24):
            hours.append(InlineKeyboardButton(
                f"{hour:02d}:00",
                callback_data=f"time_{selected_date}_{hour}_0"
            ))
            hours.append(InlineKeyboardButton(
                f"{hour:02d}:30",
                callback_data=f"time_{selected_date}_{hour}_30"
            ))
        
        # Add hours in groups of 4
        for i in range(0, len(hours), 4):
            markup.row(*hours[i:i+4])
            
        return markup

class CalendarBot:
    def __init__(self):
        self.events_db = {}
        self.calendar_ui = CalendarUI()
        self.load_events()
        
    def load_events(self):
        try:
            with open('events.json', 'r') as f:
                self.events_db = json.load(f)
        except FileNotFoundError:
            self.events_db = {}
    
    def save_events(self):
        with open('events.json', 'w') as f:
            json.dump(self.events_db, f)

    def get_google_calendar_service(self):
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, GOOGLE_CALENDAR_SCOPES)
        credentials = flow.run_local_server(port=0)
        service = build('calendar', 'v3', credentials=credentials)
        return service

    def create_event(self, user_id, event_data):
        event_id = str(len(self.events_db.get(str(user_id), [])) + 1)
        if str(user_id) not in self.events_db:
            self.events_db[str(user_id)] = {}
        self.events_db[str(user_id)][event_id] = event_data
        self.save_events()
        return event_id

    def add_to_google_calendar(self, event_data):
        service = self.get_google_calendar_service()
        event = {
            'summary': event_data['title'],
            'description': event_data.get('description', ''),
            'start': {
                'dateTime': event_data['start_time'],
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': event_data['end_time'],
                'timeZone': 'UTC',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                ],
            },
        }
        event = service.events().insert(calendarId='primary', body=event).execute()
        return event.get('htmlLink')

calendar_bot = CalendarBot()

def create_main_markup():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📅 Add Event", callback_data="add_event"),
        InlineKeyboardButton("👀 View Events", callback_data="view_events")
    )
    markup.row(
        InlineKeyboardButton("🔄 Sync with Google", callback_data="sync_google"),
        InlineKeyboardButton("⚙️ Settings", callback_data="settings")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "🎉 Welcome to the Calendar Bot!\n\n"
        "I can help you manage your events and keep track of your schedule.\n"
        "What would you like to do?",
        reply_markup=create_main_markup()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "add_event":
        msg = bot.send_message(call.message.chat.id, "📝 Please enter the event title:")
        bot.register_next_step_handler(msg, process_title_step)
    
    elif call.data == "view_events":
        show_events(call.message)
    
    elif call.data.startswith("previous-month_") or call.data.startswith("next-month_"):
        year, month = map(int, call.data.split("_")[1:])
        if call.data.startswith("previous-month_"):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        else:
            month += 1
            if month == 13:
                month = 1
                year += 1
                
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=calendar_bot.calendar_ui.create_calendar(year, month)
        )
    
    elif call.data.startswith("select-day_"):
        _, year, month, day = call.data.split("_")
        selected_date = f"{year}-{month}-{day}"
        user_states[call.message.chat.id] = {'selected_date': selected_date}
        
        bot.edit_message_text(
            "🕒 Please select the event time:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=calendar_bot.calendar_ui.create_time_selector(selected_date)
        )
    
    elif call.data.startswith("time_"):
        _, date, hour, minute = call.data.split("_")
        selected_datetime = f"{date} {hour}:{minute}"
        user_id = call.message.chat.id
        
        if user_id in user_events:
            start_time = datetime.strptime(selected_datetime, "%Y-%m-%d %H:%M")
            end_time = start_time + timedelta(hours=1)
            
            user_events[user_id].update({
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat()
            })
            
            event_id = calendar_bot.create_event(user_id, user_events[user_id])
            
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton(
                    "📱 Add to Google Calendar",
                    callback_data=f"add_to_google_{event_id}"
                )
            )
            markup.row(
                InlineKeyboardButton(
                    "🏠 Return to Main Menu",
                    callback_data="main_menu"
                )
            )
            
            bot.edit_message_text(
                f"✅ Event '{user_events[user_id]['title']}' created successfully!\n"
                f"📅 Date: {start_time.strftime('%B %d, %Y')}\n"
                f"🕒 Time: {start_time.strftime('%I:%M %p')}",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            
            # Schedule reminder
            reminder_thread = threading.Thread(
                target=schedule_reminder,
                args=(call.message.chat.id, user_events[user_id]['title'], start_time)
            )
            reminder_thread.start()
    
    elif call.data == "main_menu":
        bot.edit_message_text(
            "What would you like to do?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_main_markup()
        )
    
    elif call.data.startswith("add_to_google_"):
        event_id = call.data.split("_")[-1]
        user_id = str(call.message.chat.id)
        event_data = calendar_bot.events_db[user_id][event_id]
        
        try:
            calendar_link = calendar_bot.add_to_google_calendar(event_data)
            bot.send_message(
                call.message.chat.id,
                f"✅ Event added to Google Calendar!\n"
                f"🔗 Calendar Link: {calendar_link}",
                reply_markup=create_main_markup()
            )
        except Exception as e:
            bot.send_message(
                call.message.chat.id,
                "❌ Error adding event to Google Calendar. Please try again.",
                reply_markup=create_main_markup()
            )

def process_title_step(message):
    user_id = message.from_user.id
    user_events[user_id] = {'title': message.text}
    
    now = datetime.now()
    bot.send_message(
        message.chat.id,
        "📅 Please select the event date:",
        reply_markup=calendar_bot.calendar_ui.create_calendar(now.year, now.month)
    )

def schedule_reminder(chat_id, event_title, event_time):
    reminder_time = event_time - timedelta(minutes=30)
    delay = (reminder_time - datetime.now()).total_seconds()
    
    if delay > 0:
        time.sleep(delay)
        bot.send_message(
            chat_id,
            f"⏰ Reminder: Event '{event_title}' starts in 30 minutes!"
        )

def show_events(message):
    user_id = str(message.chat.id)
    if user_id not in calendar_bot.events_db or not calendar_bot.events_db[user_id]:
        bot.send_message(
            message.chat.id,
            "📅 You have no events scheduled.",
            reply_markup=create_main_markup()
        )
        return

    events_text = "📋 Your scheduled events:\n\n"
    for event_id, event in calendar_bot.events_db[user_id].items():
        start_time = datetime.fromisoformat(event['start_time'])
        events_text += f"📌 {event['title']}\n"
        events_text += f"   📅 {start_time.strftime('%B %d, %Y')}\n"
        events_text += f"   🕒 {start_time.strftime('%I:%M %p')}\n\n"
    
    bot.send_message(
        message.chat.id,
        events_text,
        reply_markup=create_main_markup()
    )

# Start the bot
if __name__ == "__main__":
    print("🤖 Bot started...")
    bot.polling(none_stop=True)