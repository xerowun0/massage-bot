import json
import os
import logging
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, PreCheckoutQueryHandler

# ========== SETUP ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GROUP_CHAT_ID = os.environ.get('GROUP_CHAT_ID')
USDT_WALLET = os.environ.get('USDT_WALLET')  # Your USDT wallet address
BOT_USERNAME = os.environ.get('BOT_USERNAME')  # e.g., massage_booking_bot
PAYMENT_PROVIDER_TOKEN = os.environ.get('PAYMENT_PROVIDER_TOKEN')  # Get from @BotFather

# ========== PRICING DATA ==========
SERVICES = {
    "thai": {"name": "🇹🇭 Traditional Thai Massage", "prices": {60: 900, 90: 1200, 120: 1500}},
    "oil": {"name": "💆 Oil Massage", "prices": {60: 1000, 90: 1200, 120: 1500}},
    "aroma": {"name": "🌸 Aroma Massage", "prices": {60: 1100, 90: 1300, 120: 1500}},
    "sport": {"name": "🏃 Sport Massage", "prices": {60: 1100, 90: 1300, 120: 1500}}
}

EXTRAS = {
    "nuru": {"name": "💦 Nuru Massage (with HJ)", "price": 3500},
    "hj": {"name": "✋ HJ Extra", "price": 2500},
    "bj": {"name": "👄 BJ Extra", "price": 3000},
    "anal": {"name": "🔞 Anal Extra", "price": 3000},
    "b2b": {"name": "💃 Body-to-Body Extra", "price": 4000}
}

VIP = {
    "vip_2h": {"name": "👑 1-2 Hours VIP (Everything Included)", "price": 5000},
    "vip_6h": {"name": "👑 6 Hours VIP (Everything Included)", "price": 10000},
    "vip_24h": {"name": "👑 24-Hour VIP (Everything Included)", "price": 15000}
}

# ========== CONVERSATION STATES ==========
SELECT_SERVICE, SELECT_DURATION, SELECT_LOCATION, SELECT_EXTRAS, SELECT_DATE, SELECT_TIME, CONFIRM, WAITING_PAYMENT = range(8)

# ========== TEMPORARY STORAGE ==========
bookings = {}
pending_payments = {}

# ========== HELPER FUNCTIONS ==========
def format_price(baht):
    return f"฿{baht:,}"

def baht_to_satoshis(baht):
    """Convert Baht to satoshis (1 Baht = 100 satoshis for payment)"""
    return int(baht * 100)

def generate_booking_id():
    """Generate unique booking ID"""
    return datetime.now().strftime('%Y%m%d%H%M%S') + str(int(time.time()))[-4:]

# ========== START COMMAND ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Book Massage", callback_data='book')],
        [InlineKeyboardButton("📍 Working Hours", callback_data='hours')],
        [InlineKeyboardButton("💰 Prices", callback_data='prices')],
        [InlineKeyboardButton("📋 My Bookings", callback_data='my_bookings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 **Welcome to Massage Booking!**\n\n"
        f"🕒 Operating Hours: 14:00 - 03:00 Daily\n"
        f"💵 Payments accepted via Telegram (USDT)\n\n"
        f"Choose an option:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ========== BOOKING FLOW ==========
async def book_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    for key, service in SERVICES.items():
        keyboard.append([
            InlineKeyboardButton(service['name'], callback_data=f'service_{key}')
        ])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='main_menu')])
    
    await query.edit_message_text(
        "💆 **Select Massage Type:**\n\n"
        "Choose your preferred massage:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_SERVICE

async def select_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    service_key = query.data.replace('service_', '')
    context.user_data['service_key'] = service_key
    service = SERVICES[service_key]
    
    keyboard = []
    for duration, price in service['prices'].items():
        keyboard.append([
            InlineKeyboardButton(
                f"{duration} min - {format_price(price)}", 
                callback_data=f'duration_{duration}'
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='book')])
    
    await query.edit_message_text(
        f"⏱️ **Select Duration**\n\n"
        f"Service: {service['name']}\n\n"
        f"Choose duration:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_DURATION

async def select_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    duration = int(query.data.replace('duration_', ''))
    context.user_data['duration'] = duration
    
    service = SERVICES[context.user_data['service_key']]
    price = service['prices'][duration]
    context.user_data['base_price'] = price
    
    keyboard = [
        [InlineKeyboardButton("🏠 Incall (Standard Only)", callback_data='location_incall')],
        [InlineKeyboardButton("🚗 Outcall (Extras Available)", callback_data='location_outcall')],
        [InlineKeyboardButton("🔙 Back", callback_data='book')]
    ]
    
    await query.edit_message_text(
        f"📍 **Select Location**\n\n"
        f"Service: {service['name']}\n"
        f"Duration: {duration} min\n"
        f"Price: {format_price(price)}\n\n"
        f"📍 Incall: Standard massage only\n"
        f"🚗 Outcall: Extras & VIP available\n\n"
        f"Choose:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_LOCATION

async def select_extras(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    location = query.data.replace('location_', '')
    context.user_data['location'] = location
    
    if location == 'incall':
        # Skip extras for incall
        context.user_data['selected_extras'] = []
        context.user_data['total_price'] = context.user_data['base_price']
        return await select_date(update, context)
    
    # Outcall - show extras and VIP
    keyboard = []
    
    # Show extras with + buttons
    for key, extra in EXTRAS.items():
        keyboard.append([
            InlineKeyboardButton(
                f"➕ {extra['name']} - {format_price(extra['price'])}", 
                callback_data=f'extra_{key}'
            )
        ])
    
    # VIP packages
    keyboard.append([InlineKeyboardButton("━━━ VIP Packages ━━━", callback_data='noop')])
    for key, vip in VIP.items():
        keyboard.append([
            InlineKeyboardButton(
                f"👑 {vip['name']} - {format_price(vip['price'])}", 
                callback_data=f'vip_{key}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("✅ Continue (No Extras)", callback_data='no_extras')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='book')])
    
    # Show current selections
    selected = context.user_data.get('selected_extras', [])
    vip_selected = context.user_data.get('vip_package')
    total = context.user_data['base_price']
    
    extra_text = ""
    if selected:
        extra_text = "\n\n**Selected Extras:**\n"
        for key in selected:
            extra = EXTRAS[key]
            total += extra['price']
            extra_text += f"• {extra['name']} - {format_price(extra['price'])}\n"
    
    if vip_selected:
        vip = VIP[vip_selected]
        total = vip['price']
        extra_text = f"\n\n**VIP Package Selected:**\n{vip['name']} - {format_price(vip['price'])}"
    
    context.user_data['total_price'] = total
    
    await query.edit_message_text(
        f"✨ **Add Extras (Outcall Only)**\n\n"
        f"Base Service: {format_price(context.user_data['base_price'])}\n"
        f"Current Total: {format_price(total)}{extra_text}\n\n"
        f"Select extras or VIP packages:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_EXTRAS

async def handle_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if 'selected_extras' not in context.user_data:
        context.user_data['selected_extras'] = []
    
    # Handle extra selection
    if query.data.startswith('extra_'):
        extra_key = query.data.replace('extra_', '')
        if extra_key not in context.user_data['selected_extras']:
            context.user_data['selected_extras'].append(extra_key)
        else:
            # Remove if already selected (toggle)
            context.user_data['selected_extras'].remove(extra_key)
    elif query.data.startswith('vip_'):
        vip_key = query.data.replace('vip_', '')
        if context.user_data.get('vip_package') == vip_key:
            # Deselect VIP
            del context.user_data['vip_package']
        else:
            context.user_data['vip_package'] = vip_key
            context.user_data['selected_extras'] = []
    elif query.data == 'no_extras':
        pass
    
    return await select_extras(update, context)

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query and query.data == 'no_extras':
        await query.answer()
    
    # Recalculate total
    total = context.user_data['base_price']
    if 'selected_extras' in context.user_data:
        for key in context.user_data['selected_extras']:
            total += EXTRAS[key]['price']
    if 'vip_package' in context.user_data:
        total = VIP[context.user_data['vip_package']]['price']
    context.user_data['total_price'] = total
    
    # Show date picker
    keyboard = []
    for i in range(7):
        date = datetime.now() + timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        day_name = date.strftime('%A')
        keyboard.append([
            InlineKeyboardButton(f"{day_name} - {date_str}", callback_data=f'date_{date_str}')
        ])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='book')])
    
    deposit = int(total * 0.2)
    
    if query:
        await query.edit_message_text(
            f"📅 **Select Date**\n\n"
            f"Total: {format_price(total)}\n"
            f"💵 Deposit (20%): {format_price(deposit)}\n\n"
            f"Choose a date:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    return SELECT_DATE

async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    date = query.data.replace('date_', '')
    context.user_data['booking_date'] = date
    
    # Show time slots (14:00 - 03:00)
    keyboard = []
    for hour in range(14, 24):
        time_str = f"{hour:02d}:00"
        keyboard.append([InlineKeyboardButton(f"🕐 {time_str}", callback_data=f'time_{time_str}')])
    for hour in range(0, 4):
        time_str = f"{hour:02d}:00"
        keyboard.append([InlineKeyboardButton(f"🕐 {time_str}", callback_data=f'time_{time_str}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='book')])
    
    await query.edit_message_text(
        f"⏰ **Select Time**\n\n"
        f"Date: {date}\n"
        f"Operating Hours: 14:00 - 03:00\n\n"
        f"Choose your preferred time:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_TIME

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    time = query.data.replace('time_', '')
    context.user_data['booking_time'] = time
    
    # Build summary
    service = SERVICES[context.user_data['service_key']]
    total = context.user_data['total_price']
    deposit = int(total * 0.2)
    
    summary = f"📋 **Booking Summary**\n\n"
    summary += f"💆 Service: {service['name']}\n"
    summary += f"⏱️ Duration: {context.user_data['duration']} min\n"
    summary += f"📍 Location: {context.user_data['location'].upper()}\n"
    
    if context.user_data.get('selected_extras'):
        summary += f"\n✨ **Extras:**\n"
        for key in context.user_data['selected_extras']:
            extra = EXTRAS[key]
            summary += f"• {extra['name']} - {format_price(extra['price'])}\n"
    
    if context.user_data.get('vip_package'):
        vip = VIP[context.user_data['vip_package']]
        summary += f"\n👑 VIP: {vip['name']}\n"
    
    summary += f"\n📅 Date: {context.user_data['booking_date']}\n"
    summary += f"⏰ Time: {context.user_data['booking_time']}\n"
    summary += f"\n💰 Total: {format_price(total)}\n"
    summary += f"💵 Deposit (20%): {format_price(deposit)}\n"
    summary += f"💳 Remaining: {format_price(total - deposit)} (pay on arrival)"
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm Booking", callback_data='final_confirm')],
        [InlineKeyboardButton("🔙 Back", callback_data='book')]
    ]
    
    await query.edit_message_text(
        summary,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CONFIRM

async def final_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Generate booking ID
    booking_id = generate_booking_id()
    
    # Store booking
    booking = {
        'id': booking_id,
        'user_id': update.effective_user.id,
        'username': update.effective_user.username,
        'name': update.effective_user.full_name,
        'service': context.user_data['service_key'],
        'duration': context.user_data['duration'],
        'location': context.user_data['location'],
        'extras': context.user_data.get('selected_extras', []),
        'vip': context.user_data.get('vip_package'),
        'total': context.user_data['total_price'],
        'deposit': int(context.user_data['total_price'] * 0.2),
        'date': context.user_data['booking_date'],
        'time': context.user_data['booking_time'],
        'status': 'pending',
        'deposit_paid': False,
        'created_at': datetime.now().isoformat()
    }
    
    bookings[booking_id] = booking
    
    # Send to group for approval
    await send_to_group(update, context, booking)
    
    # Notify customer
    keyboard = [
        [InlineKeyboardButton("📋 Track Status", callback_data=f'track_{booking_id}')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    
    await query.edit_message_text(
        f"✅ **Booking Request Sent!**\n\n"
        f"📋 Booking ID: #{booking_id}\n"
        f"💵 Deposit: {format_price(booking['deposit'])}\n\n"
        f"⏳ Waiting for massage lady to confirm.\n"
        f"You'll be notified once approved.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

async def send_to_group(update, context, booking):
    """Send booking to group for approval"""
    message = f"🆕 **New Booking Request**\n\n"
    message += f"👤 Customer: {booking['name']} (@{booking['username']})\n"
    message += f"📋 Booking: #{booking['id']}\n\n"
    message += f"💆 Service: {SERVICES[booking['service']]['name']}\n"
    message += f"⏱️ Duration: {booking['duration']} min\n"
    message += f"📍 Location: {booking['location'].upper()}\n"
    
    if booking['extras']:
        message += f"\n✨ **Extras:**\n"
        for key in booking['extras']:
            message += f"• {EXTRAS[key]['name']} - {format_price(EXTRAS[key]['price'])}\n"
    
    if booking['vip']:
        message += f"\n👑 VIP: {VIP[booking['vip']]['name']}\n"
    
    message += f"\n📅 Date: {booking['date']}\n"
    message += f"⏰ Time: {booking['time']}\n"
    message += f"💰 Total: {format_price(booking['total'])}\n"
    message += f"💵 Deposit: {format_price(booking['deposit'])}\n\n"
    message += f"**Actions:**"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f'accept_{booking["id"]}'),
            InlineKeyboardButton("❌ Reject", callback_data=f'reject_{booking["id"]}')
        ],
        [InlineKeyboardButton("🔄 Reschedule", callback_data=f'reschedule_{booking["id"]}')]
    ]
    
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== ADMIN ACTIONS ==========
async def admin_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    booking_id = query.data.replace('accept_', '')
    
    if booking_id in bookings:
        bookings[booking_id]['status'] = 'accepted'
        booking = bookings[booking_id]
        
        # Create payment invoice
        await send_payment_invoice(update, context, booking)
        
        # Update group message
        await query.edit_message_text(
            f"✅ **Booking Accepted!**\n\n"
            f"Booking #{booking_id}\n"
            f"💰 Deposit: {format_price(booking['deposit'])}\n"
            f"💳 Payment invoice sent to customer.\n"
            f"⏳ Waiting for payment...",
            parse_mode='Markdown'
        )

async def send_payment_invoice(update, context, booking):
    """Send Telegram payment invoice"""
    
    # Create invoice
    title = f"Massage Booking Deposit #{booking['id']}"
    description = f"""
Booking Details:
Service: {SERVICES[booking['service']]['name']}
Duration: {booking['duration']} min
Date: {booking['date']}
Time: {booking['time']}
Location: {booking['location'].upper()}

Deposit: {format_price(booking['deposit'])}
Remaining: {format_price(booking['total'] - booking['deposit'])} (pay on arrival)
"""
    
    payload = f"booking_{booking['id']}"
    currency = "USD"
    prices = [LabeledPrice("Deposit (20%)", baht_to_satoshis(booking['deposit']))]
    
    # Get user's chat ID
    user_id = booking['user_id']
    
    try:
        # Send invoice
        await context.bot.send_invoice(
            chat_id=user_id,
            title=title,
            description=description,
            payload=payload,
            provider_token=PAYMENT_PROVIDER_TOKEN,
            currency=currency,
            prices=prices,
            start_parameter="massage_booking",
            need_name=True,
            need_phone_number=True,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False
        )
        
        # Send follow-up message with manual payment option
        keyboard = [
            [InlineKeyboardButton("📤 Manual USDT Payment", callback_data=f'manual_pay_{booking["id"]}')],
            [InlineKeyboardButton("📋 Track Booking", callback_data=f'track_{booking["id"]}')]
        ]
        
        await context.bot.send_message(
            chat_id=user_id,
            text="💳 **Payment Options**\n\n"
                 "You can pay using the invoice above, or send USDT manually.\n\n"
                 f"USDT Wallet Address:\n`{USDT_WALLET}`\n\n"
                 f"Amount: {booking['deposit']} Baht (~{booking['deposit']/34:.2f} USDT)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Payment error: {e}")
        # Fallback to manual payment
        await send_manual_payment(update, context, booking)

async def send_manual_payment(update, context, booking):
    """Send manual payment instructions"""
    payment_text = f"""💵 **Deposit Required**

Booking #{booking['id']}
Amount: {format_price(booking['deposit'])}

**📤 Manual USDT Payment:**

Send exactly {booking['deposit']/34:.2f} USDT (TRC20) to:

`{USDT_WALLET}`

After sending, click the button below to confirm.

⚠️ Include the booking ID in the memo. Pay the EXACT amount."""
    
    keyboard = [
        [InlineKeyboardButton("✅ I've Sent Payment", callback_data=f'confirm_payment_{booking["id"]}')]
    ]
    
    await context.bot.send_message(
        chat_id=booking['user_id'],
        text=payment_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    booking_id = query.data.replace('reject_', '')
    
    if booking_id in bookings:
        bookings[booking_id]['status'] = 'rejected'
        booking = bookings[booking_id]
        
        await context.bot.send_message(
            chat_id=booking['user_id'],
            text=f"❌ **Booking Rejected**\n\n"
                 f"Sorry, your booking #{booking_id} has been rejected.\n\n"
                 f"Please try booking another time.",
            parse_mode='Markdown'
        )
        
        await query.edit_message_text(
            f"❌ **Booking Rejected**\n\n"
            f"Booking #{booking_id}\n"
            f"Customer has been notified.",
            parse_mode='Markdown'
        )

async def admin_reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    booking_id = query.data.replace('reschedule_', '')
    context.user_data['reschedule_id'] = booking_id
    
    keyboard = []
    for i in range(7):
        date = datetime.now() + timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        day_name = date.strftime('%A')
        keyboard.append([
            InlineKeyboardButton(f"{day_name} - {date_str}", callback_data=f'resched_date_{date_str}')
        ])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel_reschedule')])
    
    await query.edit_message_text(
        f"🔄 **Reschedule Booking**\n\n"
        f"Booking #{booking_id}\n\n"
        f"Select new date:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_TIME

async def reschedule_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    date = query.data.replace('resched_date_', '')
    context.user_data['reschedule_date'] = date
    
    keyboard = []
    for hour in range(14, 24):
        time_str = f"{hour:02d}:00"
        keyboard.append([InlineKeyboardButton(f"🕐 {time_str}", callback_data=f'resched_time_{time_str}')])
    for hour in range(0, 4):
        time_str = f"{hour:02d}:00"
        keyboard.append([InlineKeyboardButton(f"🕐 {time_str}", callback_data=f'resched_time_{time_str}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f'reschedule_{context.user_data["reschedule_id"]}')])
    
    await query.edit_message_text(
        f"🔄 **Reschedule Booking**\n\n"
        f"New Date: {date}\n\n"
        f"Select new time:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SELECT_TIME

async def reschedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    time = query.data.replace('resched_time_', '')
    booking_id = context.user_data['reschedule_id']
    new_date = context.user_data['reschedule_date']
    
    if booking_id in bookings:
        bookings[booking_id]['date'] = new_date
        bookings[booking_id]['time'] = time
        bookings[booking_id]['status'] = 'rescheduled'
        booking = bookings[booking_id]
        
        keyboard = [
            [InlineKeyboardButton("✅ Confirm New Time", callback_data=f'confirm_resched_{booking_id}')],
            [InlineKeyboardButton("❌ Cancel Booking", callback_data=f'cancel_resched_{booking_id}')]
        ]
        
        await context.bot.send_message(
            chat_id=booking['user_id'],
            text=f"🔄 **Booking Rescheduled**\n\n"
                 f"Booking #{booking_id}\n\n"
                 f"📅 New Date: {new_date}\n"
                 f"⏰ New Time: {time}\n\n"
                 f"Please confirm or cancel:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        await query.edit_message_text(
            f"✅ **Reschedule Request Sent**\n\n"
            f"Booking #{booking_id}\n"
            f"New Date: {new_date}\n"
            f"New Time: {time}\n\n"
            f"⏳ Waiting for customer confirmation...",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END

async def confirm_reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    booking_id = query.data.replace('confirm_resched_', '')
    
    if booking_id in bookings:
        bookings[booking_id]['status'] = 'accepted'
        booking = bookings[booking_id]
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"✅ **Reschedule Confirmed!**\n\n"
                 f"Booking #{booking_id}\n"
                 f"New Date: {booking['date']}\n"
                 f"New Time: {booking['time']}\n\n"
                 f"⏳ Waiting for deposit payment...",
            parse_mode='Markdown'
        )
        
        # Send payment invoice again
        await send_payment_invoice(update, context, booking)
        
        await query.edit_message_text(
            f"✅ **Reschedule Confirmed!**\n\n"
            f"Booking #{booking_id}\n"
            f"Payment invoice sent.",
            parse_mode='Markdown'
        )

async def cancel_reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    booking_id = query.data.replace('cancel_resched_', '')
    
    if booking_id in bookings:
        bookings[booking_id]['status'] = 'cancelled'
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"❌ **Booking Cancelled**\n\n"
                 f"Booking #{booking_id}\n"
                 f"Customer cancelled the booking.",
            parse_mode='Markdown'
        )
        
        await query.edit_message_text(
            f"❌ **Booking Cancelled**",
            parse_mode='Markdown'
        )

# ========== PAYMENT HANDLING ==========
async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful payment"""
    query = update.pre_checkout_query
    
    # Always approve the payment
    await query.answer(ok=True)
    
    # Payment will be handled by successful_payment_callback

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful payment"""
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    
    # Extract booking ID from payload
    booking_id = payload.replace('booking_', '')
    
    if booking_id in bookings:
        bookings[booking_id]['deposit_paid'] = True
        bookings[booking_id]['status'] = 'confirmed'
        
        # Notify customer
        booking = bookings[booking_id]
        
        await update.message.reply_text(
            f"✅ **Payment Successful!** 🎉\n\n"
            f"Booking #{booking_id} is now confirmed!\n\n"
            f"📅 Date: {booking['date']}\n"
            f"⏰ Time: {booking['time']}\n"
            f"📍 Location: {'Incall Studio' if booking['location'] == 'incall' else 'Your location'}\n\n"
            f"💳 Remaining: {format_price(booking['total'] - booking['deposit'])} (pay on arrival)\n\n"
            f"See you soon! 🌸",
            parse_mode='Markdown'
        )
        
        # Notify group
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"✅ **Payment Confirmed!** 💰\n\n"
                 f"Booking #{booking_id}\n"
                 f"Deposit paid: {format_price(booking['deposit'])}\n"
                 f"Customer: {booking['name']}\n\n"
                 f"✅ Booking is now confirmed!",
            parse_mode='Markdown'
        )

async def manual_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual payment confirmation"""
    query = update.callback_query
    await query.answer()
    
    booking_id = query.data.replace('manual_pay_', '')
    context.user_data['manual_booking_id'] = booking_id
    
    await query.edit_message_text(
        f"📤 **Manual USDT Payment**\n\n"
        f"Booking #{booking_id}\n\n"
        f"💎 Send USDT (TRC20) to:\n\n"
        f"`{USDT_WALLET}`\n\n"
        f"💰 Amount: {bookings[booking_id]['deposit']/34:.2f} USDT\n\n"
        f"After sending, type your transaction hash (TXID) below.\n\n"
        f"Example: `0x1234...5678`",
        parse_mode='Markdown'
    )
    
    return WAITING_PAYMENT

async def handle_transaction_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive transaction hash for manual payment"""
    tx_hash = update.message.text.strip()
    booking_id = context.user_data.get('manual_booking_id')
    
    if not booking_id or booking_id not in bookings:
        await update.message.reply_text(
            "❌ Booking not found. Please start over.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    booking = bookings[booking_id]
    
    # Mark as paid (you'd verify on-chain in production)
    bookings[booking_id]['deposit_paid'] = True
    bookings[booking_id]['status'] = 'confirmed'
    bookings[booking_id]['tx_hash'] = tx_hash
    
    await update.message.reply_text(
        f"✅ **Payment Confirmed!** 🎉\n\n"
        f"Booking #{booking_id} is now confirmed!\n\n"
        f"📅 Date: {booking['date']}\n"
        f"⏰ Time: {booking['time']}\n"
        f"📍 Location: {'Incall Studio' if booking['location'] == 'incall' else 'Your location'}\n\n"
        f"💳 Remaining: {format_price(booking['total'] - booking['deposit'])} (pay on arrival)\n\n"
        f"🧾 TXID: `{tx_hash[:20]}...`\n\n"
        f"See you soon! 🌸",
        parse_mode='Markdown'
    )
    
    # Notify group
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=f"✅ **Manual Payment Confirmed!** 💰\n\n"
             f"Booking #{booking_id}\n"
             f"Deposit paid: {format_price(booking['deposit'])}\n"
             f"Customer: {booking['name']}\n"
             f"TXID: `{tx_hash[:20]}...`\n\n"
             f"✅ Booking is now confirmed!",
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

# ========== TRACK BOOKING ==========
async def track_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track booking status"""
    query = update.callback_query
    await query.answer()
    
    booking_id = query.data.replace('track_', '')
    
    if booking_id not in bookings:
        await query.edit_message_text(
            "❌ Booking not found.",
            parse_mode='Markdown'
        )
        return
    
    booking = bookings[booking_id]
    
