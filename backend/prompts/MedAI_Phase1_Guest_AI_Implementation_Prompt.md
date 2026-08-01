# Med-AI Phase 1 -- Guest AI Chat Implementation Prompt

## Objective

Implement **Phase 1: Guest AI Chat** for Med-AI.

The goal is to allow anyone to use the AI medical chat **without logging
in or signing up**, while ensuring that guest users receive **general
medical guidance only**. Personalized responses remain exclusive to
authenticated users with a completed health profile.

------------------------------------------------------------------------

# Product Requirements

## User Modes

There are two chat modes:

1.  **Guest User**
2.  **Authenticated User**

Guest users can immediately start chatting.

Authenticated users continue using Personalized AI.

The application should automatically determine which mode is active.

------------------------------------------------------------------------

# Landing Page

Update the landing page.

Current CTA:

-   Login / Signup

New CTA:

Primary Button:

-   **Start Chatting**

Secondary Button:

-   **Login / Sign Up**

Clicking **Start Chatting** should:

-   Open AI Chat instantly.
-   Require no authentication.
-   Require no account creation.
-   Not display any login popup.

------------------------------------------------------------------------

# Chat Header

### Guest

Display:

-   🟢 Guest Mode

Subtitle:

-   General Medical Guidance

Button:

-   Login for Personalized AI

### Authenticated

Display:

-   🩺 Personalized AI

Subtitle:

-   Using Your Health Profile

------------------------------------------------------------------------

# Welcome Screen (Guest)

Title:

**Welcome to Med-AI**

Subtitle:

Ask medical questions, understand symptoms, learn about diseases,
medicines, and healthy living.

Information Card:

You are currently using Guest Mode.

Responses are based only on what you share during this chat.

Login to receive personalized medical guidance based on your health
profile.

CTA:

Continue Chatting

------------------------------------------------------------------------

# Chat Experience

Guest users receive:

-   Unlimited chat
-   Unlimited messages
-   No forced login
-   No session limits

Only difference:

Responses are **never personalized**.

------------------------------------------------------------------------

# Backend

Backend automatically determines mode.

If Authorization Token exists:

-   authenticated

Otherwise:

-   guest

Do not trust the frontend as the source of truth.

------------------------------------------------------------------------

# Chat API

POST /chat

Authenticated:

-   Load medical profile
-   Load chat history
-   Load reports
-   Personalized prompt

Guest:

-   Skip all profile loading
-   Use Guest Prompt
-   Temporary session only

------------------------------------------------------------------------

# Prompt Builder

Guest

System Prompt

-   

Conversation History

-   

Current Message

Authenticated

System Prompt

-   

Medical Profile

-   

Health History

-   

Conversation

-   

Message

------------------------------------------------------------------------

# Guest Sessions

Generate temporary Guest Session IDs.

Example:

guest_xxxxxxxxx

Store conversation temporarily.

Automatically expire inactive sessions.

Never permanently store guest conversations.

------------------------------------------------------------------------

# Frontend State

Maintain:

-   mode
-   guestSessionId
-   conversation
-   isAuthenticated
-   userProfile

Guest:

userProfile = null

------------------------------------------------------------------------

# Login Upgrade Card

After each AI response show a subtle card.

Want more personalized medical guidance?

Login to let Med-AI consider:

-   Medical History
-   Allergies
-   Current Medicines
-   Chronic Diseases
-   Medical Reports

Button:

Login Now

Do not interrupt chatting.

------------------------------------------------------------------------

# Suggested Prompts

-   I have a headache.
-   Explain diabetes.
-   Is fever dangerous?
-   What causes chest pain?
-   How do antibiotics work?

------------------------------------------------------------------------

# Security

Guest users must never receive:

-   Medical profile
-   Reports
-   Previous authenticated chats
-   Cached user information

------------------------------------------------------------------------

# Guest AI System Prompt

You are Med-AI, an evidence-based medical assistant.

The current user is NOT authenticated.

You have NO access to:

-   Medical history
-   Age
-   Gender
-   Allergies
-   Medications
-   Chronic illnesses
-   Previous conversations
-   Medical reports

unless the user explicitly provides that information during the current
conversation.

Rules:

-   Never claim knowledge about the user's health profile.
-   Never personalize using assumptions.
-   Explain symptoms, diseases, medicines, and treatments in general
    terms.
-   Never provide definitive diagnoses.
-   Clearly distinguish common causes from serious possibilities.
-   Highlight emergency warning signs when appropriate.
-   Recommend professional medical evaluation when needed.
-   Ask concise follow-up questions if important information is missing.
-   If a user requests personalized advice, explain that Guest Mode
    provides only general guidance and that logging in enables responses
    based on their health profile.
-   Be empathetic, calm, professional, and evidence-based.
-   End medical responses with a confidence level:
    -   High Confidence
    -   Moderate Confidence
    -   Limited Information

------------------------------------------------------------------------

# UI/UX Preservation Requirements

## IMPORTANT

This is an enhancement to the existing Med-AI application.

It is **NOT** a redesign.

Do NOT change:

-   Existing theme
-   Color palette
-   Typography
-   Fonts
-   Button styles
-   Chat UI
-   Cards
-   Navigation
-   Layout
-   Animations
-   Component styling
-   Responsive behavior
-   Existing routing unless necessary

Reuse existing:

-   Components
-   Hooks
-   Services
-   Design system
-   Styling

The authenticated experience should remain visually identical.

Only add:

-   Start Chatting button
-   Guest Mode badge
-   Login for Personalized AI button
-   Welcome card
-   Login upgrade card
-   Backend guest session support

Any new UI should blend seamlessly into the current Med-AI design
language.

The final implementation should feel like a natural extension of the
existing application rather than a redesign.

------------------------------------------------------------------------

# Code Quality

-   Maintain current architecture.
-   Avoid duplicate code.
-   Refactor shared chat logic where appropriate.
-   Use TypeScript best practices.
-   Keep the code modular.
-   Add loading states and error handling.
-   Ensure responsive UI.
-   Maintain backward compatibility.

------------------------------------------------------------------------

# Expected Outcome

Deliver a production-ready Guest AI Chat feature that:

-   Preserves the existing Med-AI UI and UX.
-   Requires no authentication.
-   Supports unlimited guest chat.
-   Never personalizes guest responses.
-   Seamlessly upgrades authenticated users to Personalized AI.
