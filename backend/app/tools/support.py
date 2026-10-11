"""
The open_support_ticket tool: the assistant hands the chat to the human support team.

The model calls it when the customer wants a person, or when the handbook says the problem
needs the support team (payment deducted, damaged item, late refund, locked account...).
Nothing is created here: the chat panel shows the ticket form (name, email, issue, files)
and the ticket opens when the customer sends it (POST /api/handoff).
"""
SPEC = {
    "name": "open_support_ticket",
    "description": (
        "Transfer the customer to the human support team by showing the support ticket form in the chat. "
        "Use it when the customer asks to talk to a person, human, agent, the support team or customer service "
        "(in any language, e.g. 'agent se baat karni hai'), or when their problem needs ShopEase staff according "
        "to the handbook (money deducted but no order after 7 working days, damaged, wrong or missing items, "
        "a late refund, an account they cannot access, or a complaint). After calling it, tell the customer to "
        "fill in the form below with their name, email and the issue, and that an agent will reply in this chat."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "One short sentence: why the customer needs a person."}
        },
        "required": ["reason"],
    },
}


def run(arguments):
    return {
        "form_shown": True,
        "next_step": "The ticket form is now shown below your reply. Ask the customer to fill in their name, "
                     "email and the issue (attachments optional) and tap 'Open ticket'. Do not ask for these "
                     "details in the chat yourself.",
        "reason": str(arguments.get("reason", ""))[:200],
    }
