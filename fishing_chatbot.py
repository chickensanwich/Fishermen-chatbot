from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from neo4j import GraphDatabase
from pydantic import BaseModel
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher
import random
from datetime import datetime
from googletrans import Translator
from gtts import gTTS
from fastapi.staticfiles import StaticFiles
import os
import glob

app = FastAPI()
# Create directory to store audio responses
os.makedirs("tts_audio", exist_ok=True)
app.mount("/tts_audio", StaticFiles(directory="tts_audio"), name="tts_audio")

# Delete old files (older than 5 files)
old_files = sorted(glob.glob("tts_audio/*.mp3"))[:-5]
for f in old_files:
    os.remove(f)

# Neo4j details
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "nej4nej4"
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Enhanced session management
sessions = {}

class ChatRequest(BaseModel):
    message: str

# conversational Enhancments

class ConversationMemory:
    """Track conversation state and context"""
    def __init__(self):
        self.messages = []
        self.entities_discussed = set()
        self.topics_discussed = set()
        self.current_topic = None
        self.user_goals = []  # Inferred goals
        self.questions_asked = []
        self.stage = "greeting"  # greeting, exploring, deep_dive, closing
        self.user_preferences = {}
        self.last_intent = None
        self.clarification_needed = False
        
    def add_message(self, role: str, content: str, intent: str = None):
        self.messages.append({
            "role": role,
            "content": content,
            "intent": intent,
            "timestamp": datetime.now()
        })
        if len(self.messages) > 10:
            self.messages = self.messages[-10:]  # Keep last 10
    
    def update_stage(self):
        """Update conversation stage based on history"""
        msg_count = len(self.messages)
        if msg_count <= 2:
            self.stage = "greeting"
        elif msg_count <= 6:
            self.stage = "exploring"
        elif msg_count <= 12:
            self.stage = "deep_dive"
        else:
            self.stage = "expert"

class Synonyms:
    """Handle word variations and synonyms"""
    
    SYNONYM_MAP = {
        "when": ["when", "what time", "timing", "best time", "season", "period"],
        "where": ["where", "location", "place", "area", "spot", "region", "find"],
        "catch": ["catch", "fishing", "fish", "get", "find", "harvest", "hunt"],
        "hilsa": ["hilsa", "ilish", "ilisha", "ilish fish"],
        "catfish": ["catfish", "cat fish", "magur"],
        "salmon": ["salmon", "salmon fish"],
        "season": ["season", "time", "period", "month"],
        "water": ["water", "river", "stream", "pond", "lake"],
        "net": ["net", "jal", "nets", "fishing net"],
        "good": ["good", "best", "ideal", "perfect", "suitable", "right"],
        "bad": ["bad", "avoid", "not good", "unsuitable", "wrong"],
        "why": ["why", "reason", "cause", "how come"],
        "what": ["what", "which", "tell me"],
        "equipment": ["equipment", "gear", "tools", "stuff", "things"],
        "cost": ["cost", "price", "money", "expense", "income"],
        "murky": ["murky", "dirty", "unclear", "muddy", "cloudy"],
        "clean": ["clean", "clear", "pure", "fresh"]
    }
    
    @staticmethod
    def normalize(word: str) -> str:
        """Convert word to canonical form"""
        word_lower = word.lower().strip()
        for canonical, variations in Synonyms.SYNONYM_MAP.items():
            if word_lower in variations:
                return canonical
        return word_lower
    
    @staticmethod
    def expand_query(query: str) -> List[str]:
        """Expand query with synonyms"""
        words = query.lower().split()
        expanded = [query]
        
        for word in words:
            normalized = Synonyms.normalize(word)
            if normalized != word and normalized in Synonyms.SYNONYM_MAP:
                # Add variation
                new_query = query.lower().replace(word, normalized)
                expanded.append(new_query)
        
        return expanded

class FuzzyMatcher:
    """Handle typos and fuzzy matching"""
    
    KNOWN_ENTITIES = {
        "fish": ["hilsa", "catfish", "salmon", "mother fish", "fish fry"],
        "seasons": ["monsoon", "winter", "summer", "spring", "autumn"],
        "months": ["boisakh", "joishtho", "falgun"],
        "locations": ["kurigram", "freshwater", "saltwater"],
        "conditions": ["murky", "clean", "tide", "current", "amavasya"],
        "gear": ["net", "darki", "current net", "rod", "tackle"]
    }
    
    @staticmethod
    def fuzzy_match(word: str, threshold: float = 0.75) -> Tuple[str, str, float]:
        """Find best fuzzy match for a word"""
        word_lower = word.lower().strip()
        best_match = None
        best_category = None
        best_score = 0
        
        for category, entities in FuzzyMatcher.KNOWN_ENTITIES.items():
            for entity in entities:
                # Calculate similarity
                score = SequenceMatcher(None, word_lower, entity).ratio()
                
                # Also check if word is contained in entity or vice versa
                if word_lower in entity or entity in word_lower:
                    score = max(score, 0.8)
                
                if score > best_score and score >= threshold:
                    best_match = entity
                    best_category = category
                    best_score = score
        
        return best_match, best_category, best_score
    
    @staticmethod
    def correct_message(message: str) -> str:
        """Auto-correct typos in message"""
        words = message.split()
        corrected = []
        
        for word in words:
            match, category, score = FuzzyMatcher.fuzzy_match(word, threshold=0.8)
            if match and score > 0.85:
                corrected.append(match)
            else:
                corrected.append(word)
        
        return " ".join(corrected)

class QuestionAnalyzer:
    """Analyze question structure and type"""
    
    @staticmethod
    def classify_question_type(message: str) -> str:
        """Determine question type"""
        msg_lower = message.lower().strip()
        
        # Yes/No questions
        if msg_lower.startswith(("is ", "are ", "can ", "should ", "do ", "does ", "will ")):
            return "yes_no"
        
        # Temporal (when)
        if msg_lower.startswith(("when ", "what time", "which season", "which month")):
            return "temporal"
        
        # Location (where)
        if msg_lower.startswith(("where ", "which place", "which location")):
            return "location"
        
        # Reason (why)
        if msg_lower.startswith(("why ", "how come", "what causes", "what makes")):
            return "reason"
        
        # Method (how)
        if msg_lower.startswith(("how ", "what way", "what method")):
            return "method"
        
        # Choice (which)
        if msg_lower.startswith(("which ", "what ", "which one")):
            return "choice"
        
        return "general"
    
    @staticmethod
    def detect_negation(message: str) -> Tuple[bool, List[str]]:
        """Detect negative questions"""
        negation_words = ["not", "don't", "dont", "avoid", "shouldn't", "shouldnt", 
                         "can't", "cant", "never", "no", "bad"]
        
        words = message.lower().split()
        for i, word in enumerate(words):
            if word in negation_words:
                context = words[max(0, i-1):min(len(words), i+4)]
                return True, context
        
        return False, []
    
    @staticmethod
    def extract_comparison(message: str) -> Optional[Tuple[str, str]]:
        """Extract entities being compared"""
        msg_lower = message.lower()
        
        comparison_patterns = [
            ("vs", "vs"),
            ("versus", "versus"),
            ("or", "or"),
            ("and", "and"),
            ("between", "between")
        ]
        
        for pattern, sep in comparison_patterns:
            if pattern in msg_lower:
                parts = msg_lower.split(pattern)
                if len(parts) >= 2:
                    return parts[0].strip(), parts[1].strip()
        
        return None

class ResponseGenerator:
    """Generate natural, varied responses"""
    
    # Response templates with personality
    TEMPLATES = {
        "greeting": [
            "Hello! I'm your fishing expert. {capability} What would you like to know?",
            "Hi there! Great to see you. {capability} How can I help you today?",
            "Hey! {capability} I'm here to help with all your fishing questions!",
        ],
        "season_answer": [
            "Perfect timing question! {fish} is best caught during {season}. {extra}",
            "Great! For {fish}, the ideal season is {season}. {extra}",
            "You'll have the best luck with {fish} in {season}. {extra}",
            "{season} is when {fish} is most abundant and active. {extra}"
        ],
        "location_answer": [
            "{fish} can be found in {location} environments. {extra}",
            "You'll find {fish} in {location} areas. {extra}",
            "Look for {fish} in {location} waters. {extra}"
        ],
        "acknowledgment": [
            "Great question!",
            "That's a smart question!",
            "Excellent!",
            "I'm glad you asked!",
            "Good thinking!"
        ],
        "follow_up": [
            "Would you like to know more about {topic}?",
            "Want to explore {topic} further?",
            "Interested in learning about {topic}?",
            "Should I tell you about {topic}?",
            "Curious about {topic}?"
        ],
        "clarification": [
            "Just to clarify, are you asking about {option}?",
            "I found information on a few topics. Did you mean {option}?",
            "To make sure I help you right, are you interested in {option}?"
        ],
        "no_data": [
            "I don't have specific data on that, but I can tell you about {alternative}!",
            "That's not in my knowledge base yet, but I know about {alternative}!",
            "I wish I had that info! But I can help with {alternative}."
        ],
        "affirmative_response": [
            "Perfect! Let me share more details.",
            "Great! Here's what I know:",
            "Absolutely! Here you go:",
            "Sure thing! Let me explain:"
        ],
        "transition": [
            "Speaking of {topic},",
            "That reminds me,",
            "Interestingly,",
            "By the way,",
            "Also worth noting,"
        ]
    }
    
    @staticmethod
    def pick_template(template_type: str, **kwargs) -> str:
        """Pick random template and format it"""
        if template_type not in ResponseGenerator.TEMPLATES:
            return ""
        
        templates = ResponseGenerator.TEMPLATES[template_type]
        template = random.choice(templates)
        
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
    
    @staticmethod
    def add_personality(response: str, stage: str) -> str:
        """Add personality based on conversation stage"""
        # Add enthusiasm in early stages
        if stage in ["greeting", "exploring"]:
            if random.random() < 0.3:  # 30% chance
                enthusiasm = random.choice(["Great! ", "Awesome! ", "Nice! "])
                response = enthusiasm + response
        
        # Add expert touch in deep stages
        if stage == "expert":
            if random.random() < 0.2:  # 20% chance
                expert = random.choice([
                    "Based on my knowledge, ",
                    "From experience, ",
                    "Here's what I know: "
                ])
                response = expert + response
        
        return response

class KnowledgeGraph:
    """Enhanced knowledge retrieval"""
    
    @staticmethod
    def get_comprehensive_info(entity_name: str) -> Dict:
        """Get all information about an entity"""
        cypher = """
        MATCH (e)
        WHERE toLower(e.name) CONTAINS toLower($entity)
        OPTIONAL MATCH (e)-[r]->(target)
        OPTIONAL MATCH (e)<-[r2]-(source)
        RETURN e.name AS entity, 
               labels(e) AS entity_labels,
               type(r) AS outgoing_relation, 
               target.name AS target_name,
               labels(target) AS target_labels,
               type(r2) AS incoming_relation,
               source.name AS source_name,
               labels(source) AS source_labels
        LIMIT 50
        """
        
        with driver.session() as session:
            results = session.run(cypher, entity=entity_name)
            data = {
                "entity": None,
                "labels": [],
                "outgoing": [],
                "incoming": []
            }
            
            for record in results:
                if not data["entity"]:
                    data["entity"] = record["entity"]
                    data["labels"] = record["entity_labels"] or []
                
                if record["outgoing_relation"] and record["target_name"]:
                    data["outgoing"].append({
                        "relation": record["outgoing_relation"],
                        "target": record["target_name"],
                        "labels": record["target_labels"] or []
                    })
                
                if record["incoming_relation"] and record["source_name"]:
                    data["incoming"].append({
                        "relation": record["incoming_relation"],
                        "source": record["source_name"],
                        "labels": record["source_labels"] or []
                    })
            
            return data
    
    @staticmethod
    def get_suggestions(current_entity: str, discussed_topics: set) -> List[str]:
        """Get related topics user might be interested in"""
        info = KnowledgeGraph.get_comprehensive_info(current_entity)
        suggestions = []
        
        # Get related entities
        for rel in info["outgoing"]:
            topic = rel["target"]
            if topic not in discussed_topics and topic != current_entity:
                suggestions.append(topic)
        
        for rel in info["incoming"]:
            topic = rel["source"]
            if topic not in discussed_topics and topic != current_entity:
                suggestions.append(topic)
        
        return suggestions[:3]  # Top 3 suggestions

class SmartIntentClassifier:
    """Enhanced intent classification"""
    
    @staticmethod
    def classify(message: str, entities: Dict, memory: ConversationMemory) -> str:
        """Classify intent with context"""
        msg_lower = message.lower().strip()
        question_type = QuestionAnalyzer.classify_question_type(message)
        is_negative, neg_context = QuestionAnalyzer.detect_negation(message)
        
        # Short responses
        if msg_lower in ["yes", "yeah", "yep", "sure", "ok", "okay", "y", "ha", "haan", "please"]:
            return "affirmative"
        if msg_lower in ["no", "nope", "nah", "na", "not really"]:
            return "negative"
        if msg_lower in ["hi", "hello", "hey", "namaste", "good morning", "good evening", "greetings"]:
            return "greeting"
        if msg_lower in ["bye", "goodbye", "see you", "thanks", "thank you", "bye bye"]:
            return "goodbye"
        
        # Question type based classification
        if question_type == "temporal":
            return "season_timing"
        elif question_type == "location":
            return "location"
        elif question_type == "reason":
            return "causes"
        elif question_type == "method":
            return "advice"
        elif question_type == "yes_no":
            if is_negative:
                return "suitability"
            return "suitability"
        
        # Entity-based classification
        if entities.get("water_quality"):
            return "water_condition"
        if entities.get("gear") and entities.get("fish"):
            return "gear_equipment"
        if entities.get("economic"):
            return "economic"
        
        # Comparison detection
        if QuestionAnalyzer.extract_comparison(message):
            return "comparison"
        
        # Pattern matching
        patterns = {
            "gear_equipment": ["net", "gear", "equipment", "use", "tackle", "rod"],
            "water_condition": ["murky", "clean", "water quality", "dirty"],
            "weather_condition": ["weather", "tide", "current", "wind", "rain"],
            "causes": ["why", "cause", "reason", "because"],
            "effects": ["effect", "happen", "result", "consequence"],
            "suitability": ["suitable", "good", "bad", "should", "can i"],
            "advice": ["recommend", "suggest", "tip", "best", "how to"],
            "comparison": ["compare", "difference", "versus", "vs", "better"]
        }
        
        for intent, keywords in patterns.items():
            if any(kw in msg_lower for kw in keywords):
                return intent
        
        return "general_info"

class ConversationalResponseBuilder:
    """Build context-aware conversational responses"""
    
    @staticmethod
    def build_response(intent: str, entities: Dict, memory: ConversationMemory, 
                      message: str) -> str:
        """Build intelligent, context-aware response"""
        
        # Update memory
        memory.update_stage()
        
        # Get primary entity
        primary_entity = ConversationalResponseBuilder._get_primary_entity(
            entities, memory)
        
        # Route to handlers
        handlers = {
            "greeting": ConversationalResponseBuilder._handle_greeting,
            "goodbye": ConversationalResponseBuilder._handle_goodbye,
            "affirmative": ConversationalResponseBuilder._handle_affirmative,
            "negative": ConversationalResponseBuilder._handle_negative,
            "season_timing": ConversationalResponseBuilder._handle_season,
            "location": ConversationalResponseBuilder._handle_location,
            "water_condition": ConversationalResponseBuilder._handle_water_condition,
            "weather_condition": ConversationalResponseBuilder._handle_weather,
            "gear_equipment": ConversationalResponseBuilder._handle_gear,
            "causes": ConversationalResponseBuilder._handle_causes,
            "effects": ConversationalResponseBuilder._handle_effects,
            "suitability": ConversationalResponseBuilder._handle_suitability,
            "economic": ConversationalResponseBuilder._handle_economic,
            "comparison": ConversationalResponseBuilder._handle_comparison,
            "advice": ConversationalResponseBuilder._handle_advice,
            "general_info": ConversationalResponseBuilder._handle_general
        }
        
        handler = handlers.get(intent, ConversationalResponseBuilder._handle_general)
        response = handler(primary_entity, entities, memory, message)
        
        # Add personality
        response = ResponseGenerator.add_personality(response, memory.stage)
        
        # Add proactive suggestions based on stage
        if memory.stage in ["exploring", "deep_dive"]:
            response = ConversationalResponseBuilder._add_suggestions(
                response, primary_entity, memory)
        
        return response
    
    @staticmethod
    def _get_primary_entity(entities: Dict, memory: ConversationMemory) -> str:
        """Get primary entity from message or context"""
        # Priority order
        for key in ["fish", "conditions", "water_quality", "gear", "locations", "months", "seasons"]:
            if entities.get(key):
                entity = entities[key][0]
                memory.current_topic = entity
                memory.entities_discussed.add(entity)
                return entity
        
        # Fall back to memory
        if memory.current_topic:
            return memory.current_topic
        
        return None
    
    @staticmethod
    def _handle_greeting(entity, entities, memory, message):
        capability = "I specialize in fishing - fish species, seasons, locations, water conditions, and equipment."
        greeting = ResponseGenerator.pick_template("greeting", capability=capability)
        memory.stage = "greeting"
        return greeting
    
    @staticmethod
    def _handle_goodbye(entity, entities, memory, message):
        farewells = [
            "Happy fishing!Feel free to come back anytime with more questions.",
            "Good luck with your fishing!Hope to chat again soon.",
            "Tight lines!Come back if you need more fishing wisdom.",
            "May your nets be full!See you next time."
        ]
        return random.choice(farewells)
    
    @staticmethod
    def _handle_affirmative(entity, entities, memory, message):
        if not entity:
            return "Great! What would you like to know more about?"
        
        intro = ResponseGenerator.pick_template("affirmative_response")
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        if not info["entity"]:
            return f"{intro} Actually, let me know what specific aspect interests you!"
        
        response = f"{intro}\n\n"
        response += ConversationalResponseBuilder._build_comprehensive_info(info)
        
        return response
    
    @staticmethod
    def _handle_negative(entity, entities, memory, message):
        responses = [
            "No problem! What else would you like to know about fishing?",
            "That's okay! Feel free to ask me anything else about fishing.",
            "Sure thing! Is there something else I can help you with?"
        ]
        return random.choice(responses)
    
    @staticmethod
    def _handle_season(entity, entities, memory, message):
        if not entity:
            return "I'd love to help with timing! Which fish are you interested in - Hilsa, Catfish, or Salmon?"
        
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        if not info["entity"]:
            return f"I don't have timing information for '{entity}'. Try asking about Hilsa, Catfish, or Salmon!"
        
        # Get season data
        seasons = [r["target"] for r in info["outgoing"] if r["relation"] == "SEASONALLY_AVAILABLE_IN"]
        catch_in = [r["target"] for r in info["outgoing"] if r["relation"] == "CATCH_IN"]
        
        if seasons:
            extra = ""
            if catch_in:
                extra = f"Best conditions: {', '.join(catch_in[:2])}."
            
            response = ResponseGenerator.pick_template(
                "season_answer",
                fish=info["entity"],
                season=", ".join(seasons),
                extra=extra
            )
        else:
            response = f"I don't have specific season data for {info['entity']}, but I can tell you about locations or conditions!"
        
        # Add follow-up
        follow_up = ResponseGenerator.pick_template("follow_up", topic="the best locations")
        response += f"\n\n{follow_up}"
        
        return response
    
    @staticmethod
    def _handle_location(entity, entities, memory, message):
        if not entity:
            return "Which fish are you looking to find? Hilsa, Catfish, or Salmon?"
        
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        if not info["entity"]:
            return f"I don't have location info for '{entity}'."
        
        found_in = [r["target"] for r in info["outgoing"] if r["relation"] == "FOUND_IN"]
        available_in = [r["target"] for r in info["outgoing"] if r["relation"] == "AVAILABLE_IN"]
        
        if found_in or available_in:
            location = ", ".join(found_in + available_in)
            extra = ""
            if "Freshwater" in location:
                extra = "Look in rivers, streams, and lakes."
            elif "Saltwater" in location:
                extra = "Found in coastal and estuarine areas."
            
            response = ResponseGenerator.pick_template(
                "location_answer",
                fish=info["entity"],
                location=location,
                extra=extra
            )
        else:
            response = f"Location data not available for {info['entity']}, but I can help with seasons or conditions!"
        
        # Add follow-up
        follow_up = ResponseGenerator.pick_template("follow_up", topic="water conditions")
        response += f"\n\n{follow_up}"
        
        return response
    
    @staticmethod
    def _handle_water_condition(entity, entities, memory, message):
        # Check for murky water specifically
        if any("murky" in e for e in entities.get("water_quality", [])):
            return ConversationalResponseBuilder._murky_water_analysis()
        
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        response = f"Water Condition: {entity.title() if entity else 'General'}\n\n"
        
        # Get causes
        causes = [r["target"] for r in info["outgoing"] if r["relation"] == "CAUSED_BY"]
        if causes:
            response += "What causes it:\n"
            for cause in causes[:4]:
                response += f"  • {cause}\n"
            response += "\n"
        
        # Get suitability
        suitable = [r["target"] for r in info["outgoing"] if r["relation"] == "SUITABLE_FOR"]
        not_suitable = [r["target"] for r in info["outgoing"] if r["relation"] == "NOT_SUITABLE_FOR"]
        
        if suitable:
            response += f"Good for: {', '.join(suitable)}\n"
        if not_suitable:
            response += f"Not good for: {', '.join(not_suitable)}\n"
        
        response += "\n Tip: Always check water conditions before heading out!"
        
        return response
    
    @staticmethod
    def _murky_water_analysis():
        info = KnowledgeGraph.get_comprehensive_info("Murky Water")
        
        response = "About Murky Water\n\n"
        
        causes = [r["target"] for r in info["outgoing"] if r["relation"] == "CAUSED_BY"]
        if causes:
            response += "Common Causes:\n"
            for i, cause in enumerate(causes, 1):
                response += f"{i}. {cause}\n"
            response += "\n"
        
        response += "Impact on Fishing:\n"
        response += "Murky water makes fishing very difficult\n"
        response += "Fish can't see bait/nets properly\n"
        response += "Not suitable for fish catching\n\n"
        
        response += "Recommendation: Wait for clean, stable water for better results!"
        
        return response
    
    @staticmethod
    def _handle_weather(entity, entities, memory, message):
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        response = f"Condition: {entity.title() if entity else 'Weather'}\n\n"
        
        suitable = [r["target"] for r in info["outgoing"] if r["relation"] == "SUITABLE_FOR"]
        not_suitable = [r["target"] for r in info["outgoing"] if r["relation"] == "NOT_SUITABLE_FOR"]
        
        if suitable:
            response += f"Good for: {', '.join(suitable)}\n"
        if not_suitable:
            response += f"Avoid for: {', '.join(not_suitable)}\n"
        
        # Special cases
        if entity and "current" in entity.lower():
            response += "\n Warning: Strong currents can be dangerous - nets may overturn!"
        elif entity and "amavasya" in entity.lower():
            response += "\n Special Note: Amavasya (new moon) is great for Hilsa fishing!"
        
        return response
    
    @staticmethod
    def _handle_gear(entity, entities, memory, message):
        fish_mentions = entities.get("fish", [])
        gear_mentions = entities.get("gear", [])
        
        # Check for harmful gear
        if any(g in ["current net", "darki"] for g in gear_mentions):
            return ConversationalResponseBuilder._harmful_gear_warning()
        
        # Asking about net for specific fish
        if fish_mentions:
            fish_name = fish_mentions[0].title()
            
            response = f"Equipment for {fish_name}\n\n"
            
            # Check knowledge graph
            info = KnowledgeGraph.get_comprehensive_info(fish_mentions[0])
            requires = [r["target"] for r in info["outgoing"] if r["relation"] == "REQUIRES"]
            
            if requires:
                response += f"Recommended: {', '.join(requires)}\n\n"
            else:
                response += "General Guidelines:\n"
                response += "  • Use traditional fishing nets with appropriate mesh size\n"
                response += "  • Avoid Current Nets (Darki) - harmful to fish populations\n"
                response += "  • Match your gear to water type (fresh/salt)\n"
                response += "  • Allow young fish to escape and grow\n\n"
            
            response += " Want to know the best season or location too?"
            return response
        
        return "What kind of equipment are you interested in? Nets, rods, or gear for a specific fish?"
    
    @staticmethod
    def _harmful_gear_warning():
        return """ Important Warning: Current Nets (Darki)

 These nets are HARMFUL and should be avoided!

 Why they're problematic:
  • Catch mother fish and young fry indiscriminately
  • Damage fish populations long-term
  • Can overturn in strong currents
  • Not sustainable for fishing communities

    Better Alternative: Use traditional, selective nets that:
    Allow young fish to escape
    Target adult fish appropriately
    Support sustainable fishing

Want to know about better fishing practices?"""
    
    @staticmethod
    def _handle_causes(entity, entities, memory, message):
        if not entity:
            return "What would you like to know the cause of? Water conditions, seasonal changes, or something else?"
        
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        causes = [r["target"] for r in info["outgoing"] if r["relation"] == "CAUSED_BY"]
        
        if causes:
            response = f"What Causes {entity.title()}?\n\n"
            for i, cause in enumerate(causes, 1):
                response += f"{i}. {cause}\n"
            
            response += "\n Understanding causes helps you plan better fishing trips!"
            return response
        
        return f"I don't have specific cause information for {entity}, but I can tell you about its effects or how it impacts fishing!"
    
    @staticmethod
    def _handle_effects(entity, entities, memory, message):
        if not entity:
            return "What effects are you curious about? I can explain impacts of weather, water conditions, or equipment."
        
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        response = f"Effects of {entity.title()}\n\n"
        
        # Direct effects
        effects = [r["target"] for r in info["outgoing"] if r["relation"] == "CAUSES"]
        if effects:
            response += "Direct Effects:\n"
            for effect in effects:
                response += f"  • {effect}\n"
            response += "\n"
        
        # What it's not suitable for
        not_suitable = [r["target"] for r in info["outgoing"] if r["relation"] == "NOT_SUITABLE_FOR"]
        if not_suitable:
            response += "Negative Impact:\n"
            for item in not_suitable:
                response += f"   {item}\n"
            response += "\n"
        
        if not effects and not not_suitable:
            response += "I don't have specific effect data, but I can tell you about causes or suitability!\n"
        
        response += "\n Knowing effects helps you avoid bad conditions!"
        return response
    
    @staticmethod
    def _handle_suitability(entity, entities, memory, message):
        is_negative, _ = QuestionAnalyzer.detect_negation(message)
        
        if not entity:
            return "What are you checking suitability for? A fish, season, water condition, or equipment?"
        
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        response = f"Suitability: {entity.title()}\n\n"
        
        suitable = [r["target"] for r in info["outgoing"] if r["relation"] == "SUITABLE_FOR"]
        not_suitable = [r["target"] for r in info["outgoing"] if r["relation"] == "NOT_SUITABLE_FOR"]
        
        if suitable:
            response += "GOOD FOR:\n"
            for item in suitable:
                response += f"  • {item}\n"
            response += "\n"
        
        if not_suitable:
            response += "NOT GOOD FOR:\n"
            for item in not_suitable:
                response += f"  • {item}\n"
            response += "\n"
        
        # Add recommendation based on results
        if is_negative and not_suitable:
            response += f"You're right to avoid {entity} for those activities!"
        elif suitable:
            response += f"{entity.title()} is a good choice for these activities!"
        else:
            response += "Plan your activities based on suitable conditions!"
        
        return response
    
    @staticmethod
    def _handle_economic(entity, entities, memory, message):
        info = KnowledgeGraph.get_comprehensive_info("Income")
        
        response = "Economics of Fishing\n\n"
        
        divided_to = [r["target"] for r in info["outgoing"] if r["relation"] == "DIVIDED_TO"]
        
        if divided_to:
            response += "Income Distribution:\n"
            for party in divided_to:
                response += f"  • {party}\n"
            response += "\n"
            response += "Fishing income is typically shared among boat owners, fishermen, "
            response += "and covers operational costs like engine fuel and food.\n\n"
        
        response += "Understanding economics helps plan sustainable fishing ventures!"
        
        return response
    
    @staticmethod
    def _handle_comparison(entity, entities, memory, message):
        comparison = QuestionAnalyzer.extract_comparison(message)
        fish_list = entities.get("fish", [])
        
        if len(fish_list) < 2 and not comparison:
            return "To compare, please mention two fish species (like 'Hilsa and Catfish') or two conditions!"
        
        fish1 = fish_list[0] if fish_list else (comparison[0] if comparison else None)
        fish2 = fish_list[1] if len(fish_list) > 1 else (comparison[1] if comparison else None)
        
        if not fish1 or not fish2:
            return "I need two things to compare. Try 'Compare Hilsa and Salmon' or 'Hilsa vs Catfish'."
        
        info1 = KnowledgeGraph.get_comprehensive_info(fish1)
        info2 = KnowledgeGraph.get_comprehensive_info(fish2)
        
        response = f"Comparing {fish1.title()} vs {fish2.title()}\n\n"
        
        # Compare seasons
        seasons1 = [r["target"] for r in info1["outgoing"] if r["relation"] == "SEASONALLY_AVAILABLE_IN"]
        seasons2 = [r["target"] for r in info2["outgoing"] if r["relation"] == "SEASONALLY_AVAILABLE_IN"]
        
        response += "Best Season:\n"
        response += f"  • {fish1.title()}: {', '.join(seasons1) if seasons1 else 'N/A'}\n"
        response += f"  • {fish2.title()}: {', '.join(seasons2) if seasons2 else 'N/A'}\n\n"
        
        # Compare locations
        locs1 = [r["target"] for r in info1["outgoing"] if r["relation"] == "FOUND_IN"]
        locs2 = [r["target"] for r in info2["outgoing"] if r["relation"] == "FOUND_IN"]
        
        response += "Habitat:\n"
        response += f"  • {fish1.title()}: {', '.join(locs1) if locs1 else 'N/A'}\n"
        response += f"  • {fish2.title()}: {', '.join(locs2) if locs2 else 'N/A'}\n\n"
        
        # Add insight
        if seasons1 and seasons2 and seasons1 != seasons2:
            response += "Key Difference: These fish are active in different seasons, so you can target them at different times of the year!"
        elif locs1 and locs2 and locs1 != locs2:
            response += "Key Difference: These fish live in different water types, so you'll need different locations!"
        
        return response
    
    @staticmethod
    def _handle_advice(entity, entities, memory, message):
        if not entity:
            return "I'd love to give advice! What are you planning - catching a specific fish, dealing with weather, or choosing equipment?"
        
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        response = f"Fishing Advice: {entity.title()}\n\n"
        
        # Get comprehensive info
        seasons = [r["target"] for r in info["outgoing"] if r["relation"] == "SEASONALLY_AVAILABLE_IN"]
        locations = [r["target"] for r in info["outgoing"] if r["relation"] == "FOUND_IN"]
        catch_conditions = [r["target"] for r in info["outgoing"] if r["relation"] == "CATCH_IN"]
        
        if seasons:
            response += f"Best Timing: Target {entity} during {', '.join(seasons)}\n\n"
        
        if locations:
            response += f"Where to Go: Focus on {', '.join(locations)} areas\n\n"
        
        if catch_conditions:
            response += f"Ideal Conditions: Look for {', '.join(catch_conditions)}\n\n"
        
        # General tips
        response += "Pro Tips:\n"
        response += "Check water conditions before going out\n"
        response += "Avoid murky water and strong currents\n"
        response += "Use appropriate, sustainable gear\n"
        response += "Consider Bangla months: Boisakh is best\n"
        
        return response
    
    @staticmethod
    def _handle_general(entity, entities, memory, message):
        if not entity:
            return "I'm here to help! Ask me about fish species (Hilsa, Catfish, Salmon), seasons, locations, water conditions, or equipment."
        
        info = KnowledgeGraph.get_comprehensive_info(entity)
        
        if not info["entity"]:
            # Try fuzzy match
            corrected = FuzzyMatcher.correct_message(entity)
            if corrected != entity:
                return f"Did you mean '{corrected}'? Let me know and I'll tell you all about it!"
            return f"I couldn't find '{entity}' in my knowledge base. Try asking about Hilsa, Catfish, Salmon, water conditions, or equipment!"
        
        response = f"About {info['entity']}\n\n"
        
        # Categorize information
        seasons = []
        locations = []
        conditions = []
        suitable = []
        not_suitable = []
        
        for rel in info["outgoing"]:
            if rel["relation"] == "SEASONALLY_AVAILABLE_IN":
                seasons.append(rel["target"])
            elif rel["relation"] in ["FOUND_IN", "AVAILABLE_IN"]:
                locations.append(rel["target"])
            elif rel["relation"] in ["CATCH_IN", "AFFECTED_BY"]:
                conditions.append(rel["target"])
            elif rel["relation"] == "SUITABLE_FOR":
                suitable.append(rel["target"])
            elif rel["relation"] == "NOT_SUITABLE_FOR":
                not_suitable.append(rel["target"])
        
        # Build response
        if seasons:
            response += f"Season: {', '.join(set(seasons))}\n"
        if locations:
            response += f"Location: {', '.join(set(locations))}\n"
        if conditions:
            response += f"Conditions: {', '.join(set(conditions))}\n"
        if suitable:
            response += f"Good for: {', '.join(set(suitable))}\n"
        if not_suitable:
            response += f"Not good for: {', '.join(set(not_suitable))}\n"
        
        if not any([seasons, locations, conditions, suitable, not_suitable]):
            response += "I have this in my database, but limited details. Ask me something specific about it!\n"
        
        response += "\n What else would you like to know?"
        
        return response
    
    @staticmethod
    def _build_comprehensive_info(info: Dict) -> str:
        """Build comprehensive information response"""
        response = f"{info['entity']}\n\n"
        
        seasons = [r["target"] for r in info["outgoing"] if r["relation"] == "SEASONALLY_AVAILABLE_IN"]
        locations = [r["target"] for r in info["outgoing"] if r["relation"] == "FOUND_IN"]
        conditions = [r["target"] for r in info["outgoing"] if r["relation"] == "CATCH_IN"]
        
        if seasons:
            response += f"Season: {', '.join(seasons)}\n"
        if locations:
            response += f"Location: {','.join(locations)}\n"
        if conditions:
            response += f"Best Conditions: {', '.join(conditions)}\n"
        
        return response
    
    @staticmethod
    def _add_suggestions(response: str, entity: str, memory: ConversationMemory) -> str:
        """Add proactive suggestions"""
        if not entity:
            return response
        
        suggestions = KnowledgeGraph.get_suggestions(entity, memory.topics_discussed)
        
        if suggestions and random.random() < 0.6:  # 60% chance
            response += "\n\n"
            transition = ResponseGenerator.pick_template("transition", topic=suggestions[0])
            response += f"{transition} you might also want to know about {suggestions[0]}."
        
        return response

# ============= MAIN QUERY PROCESSOR =============

def process_conversation(message: str, session_id: str) -> str:
    """Main conversation processor with all enhancements"""
    
    # Get or create session memory
    if session_id not in sessions:
        sessions[session_id] = ConversationMemory()
    
    memory = sessions[session_id]
    
    # Auto-correct typos
    corrected_message = FuzzyMatcher.correct_message(message)
    
    # Expand with synonyms
    expanded_queries = Synonyms.expand_query(corrected_message)
    
    # Extract entities (try original and corrected)
    entities = {
        "fish": [],
        "seasons": [],
        "months": [],
        "locations": [],
        "conditions": [],
        "gear": [],
        "water_quality": [],
        "economic": []
    }
    
    # Extract from corrected message
    for fish in FuzzyMatcher.KNOWN_ENTITIES["fish"]:
        if fish in corrected_message.lower():
            entities["fish"].append(fish)
    
    for season in FuzzyMatcher.KNOWN_ENTITIES["seasons"]:
        if season in corrected_message.lower():
            entities["seasons"].append(season)
    
    for month in FuzzyMatcher.KNOWN_ENTITIES["months"]:
        if month in corrected_message.lower():
            entities["months"].append(month)
    
    for loc in FuzzyMatcher.KNOWN_ENTITIES["locations"]:
        if loc in corrected_message.lower():
            entities["locations"].append(loc)
    
    for cond in FuzzyMatcher.KNOWN_ENTITIES["conditions"]:
        if cond in corrected_message.lower():
            entities["conditions"].append(cond)
            if cond in ["murky", "clean"]:
                entities["water_quality"].append(cond)
    
    for gear in FuzzyMatcher.KNOWN_ENTITIES["gear"]:
        if gear in corrected_message.lower():
            entities["gear"].append(gear)
    
    if any(word in corrected_message.lower() for word in ["income", "cost", "money", "profit"]):
        entities["economic"].append("income")
    
    # Classify intent
    intent = SmartIntentClassifier.classify(corrected_message, entities, memory)
    
    # Build response
    response = ConversationalResponseBuilder.build_response(
        intent, entities, memory, corrected_message)
    
    # Update memory
    memory.add_message("user", message, intent)
    memory.add_message("assistant", response, intent)
    memory.last_intent = intent
    
    # Update topics
    if memory.current_topic:
        memory.topics_discussed.add(memory.current_topic)
    
    return response
translator = Translator()

@app.post("/chat")
async def chat(request: ChatRequest, session: Request):
    session_id = session.client.host
    user_message = request.message.strip()

    # Detect language
    detected = translator.detect(user_message)
    is_bengali_input = detected.lang == "bn"

    # Translate Bengali input to English for processing
    if is_bengali_input:
        message_en = translator.translate(user_message, src="bn", dest="en").text
    else:
        message_en = user_message

    # Process chatbot logic in English
    reply_en = process_conversation(message_en, session_id)

    # If Bengali input, translate back
    if is_bengali_input:
        reply_text = translator.translate(reply_en, src="en", dest="bn").text
        reply_lang = "bn"
    else:
        reply_text = reply_en
        reply_lang = "en"

    # Generate TTS if Bengali
    audio_path = None
    if reply_lang == "bn":
        tts = gTTS(reply_text, lang="bn")
        filename = f"tts_audio/reply_{session_id}_{int(datetime.now().timestamp())}.mp3"
        tts.save(filename)
        audio_path = f"/tts_audio/{os.path.basename(filename)}"

    return JSONResponse({
        "reply": reply_text,
        "audio_url": audio_path,
        "lang": reply_lang
    })

from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory=".", html=True), name="static")