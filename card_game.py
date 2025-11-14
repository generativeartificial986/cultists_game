# -*- coding: utf-8 -*-
"""Core Game Logic (card_game.py) - Deck Composition Update"""

import random
import time
import uuid

# MODIFIED: This new dictionary controls the number of each card in the decks.
# You can now easily tweak the quantities here.
DECK_COMPOSITION = {
    # --- Living Player Cards ---
    "Mark of the Beast": 40,
    "Compulsion": 40,
    "Third Eye": 80,
    "Harbinger of Doom": 20,
    "Lazarus": 50,
    "I Saw the Light": 100,
    "Violent Delights": 60,
    "Covet": 60,
    "Immolation": 50,
    "Act of God": 40,
    "Feed the Maggots": 40,
    "Screams from the Void": 40,
    "False Idol": 30,
    "Extended Delirium": 40,
    "Silver Tongue": 50,
    "Delirium": 80,
    "Silence": 90,
    "The Apocalypse": 30, 
    "Doppelgänger": 20,
    "Resurrection Ritual": 100,

    # --- Dead Player Cards ---
    "Oh God, Please! Anything But This!": 30,
    "Ghostly Silence": 50,
}



CARD_DEFINITIONS = {
    "Mark of the Beast": {
        "name": "Mark of the Beast",
        "description": "The names of those who killed you will be publicly announced the Morning following your death. Lasts for three rounds.",
        "phase_restriction": ["Evening"],
        "target_type": "self",
        "effect_type": "mark_of_the_beast",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 2,
        "dead_card": False,
        "duration_rounds": 3,
    },
    "Resurrection Ritual": {
        "name": "Resurrection Ritual",
        "description": "Sacrifice 1 card. Select 1 dead player to resurrect and 3 living players to assist. The assistants will be asked to sacrifice 2 cards. If all 3 assistants agree, the player is resurrected. If any assistant sabotages the ritual, it fails, and all sacrificed cards are lost.",
        "phase_restriction": ["Evening"],
        "target_type": "multi_target_ritual", # This is a new custom type
        "effect_type": "resurrection_ritual_start",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 1,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Doppelgänger": {
        "name": "Doppelgänger",
        "description": "Select a living player. If that player dies, you will secretly take their role after their death. You will lose your current hand and gain their final living hand. If you die before your target, this effect is cancelled.",
        "phase_restriction": ["Any"],
        "target_type": "other_player",
        "effect_type": "doppelganger",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 3,
        "dead_card": False,
        "duration_rounds": 0, # The effect is stored in a status effect
    },
    "Hand of Glory": {
        "name": "Hand of Glory",
        "description": "This macabre artifact capable prevents Cultists for killing you for one Night! The Cultists cannot see if you use this card. The flames of the Hand extinguish by Morning and this card may only be played once per game. Use it wisely!",
        "phase_restriction": ["Evening"], # 
        "target_type": "self",
        "effect_type": "hand_of_glory",   # This is a new, unique effect type
        "is_public": False,             # 
        "reveals_player": False,        #
        "sacrifice_cards": 0,           # 
        "dead_card": False,
        "duration_rounds": 1,           # It lasts for 1 night's resolution
    },
    "Oh God, Please! Anything But This!": {
        "name": "Oh God, Please! Anything But This!",
        "description": "Command a player to sing Mariah Carey’s 1994 hit song \"All I Want for Christmas Is You\" repeatedly, giving the Villagers a very good reason to vote to kill them. They may speak, but only to the tune of the song. Wears off at the next sundown.",
        "phase_restriction": ["Any"],
        "target_type": "other_player",
        "effect_type": "eternal_winter",
        "is_public": False,
        "reveals_player": True,
        "sacrifice_cards": 0,
        "dead_card": True,
        "duration_rounds": 1,
    },
    "Compulsion": {
        "name": "Compulsion",
        "description": "Force one of the Cultists to say the word \"Cultist\" at least once before the next sundown or else they will be killed.",
        "phase_restriction": ["Evening"],
        "target_type": "other",
        "effect_type": "compulsion",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 3,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Third Eye": {
        "name": "Third Eye",
        "description": "Select one player and secretly look at all cards in their hand. If the player you select is a Cultist, they will be notified that you looked at their cards.",
        "phase_restriction": ["Evening"],
        "target_type": "other_player",  # <-- CHANGED
        "effect_type": "third_eye",
        "is_public": False,             # <-- CHANGED
        "reveals_player": False,        # <-- CHANGED
        "sacrifice_cards": 1,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Harbinger of Doom": {
        "name": "Harbinger of Doom",
        "description": "Perform a blood ritual to kill another player. Three rounds after this card is played, you will select the person to kill during the Night. However, this card will be announced when played.",
        "phase_restriction": ["Evening"],
        "target_type": "self",
        "effect_type": "harbinger_of_doom",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 3,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Lazarus": {
        "name": "Lazarus",
        "description": "Temporarily resurrect yourself to participate in voting, but you cannot speak or use any cards. You will die again at sundown.",
        "phase_restriction": ["Any"],
        "target_type": "self",
        "effect_type": "lazarus",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 0,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "I Saw the Light": {
        "name": "I Saw the Light",
        "description": "Cleanse any poisons or illness. Can prevent death by voting. Lasts until the next sundown. May be played on yourself.",
        "phase_restriction": ["Any"],
        "target_type": "other_player",
        "effect_type": "i_saw_the_light",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 3,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Violent Delights": {
        "name": "Violent Delights",
        "description": "Participate directly or indirectly (such as by voting) in the death of another player within two rounds of playing this card, and earn two extra cards during the following Morning. However, playing this card will be announced after you succeed or fail, and failing to kill anyone will cause you to lose two random cards!",
        "phase_restriction": ["Evening"],
        "target_type": "self",
        "effect_type": "violent_delights",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 1,
        "dead_card": False,
        "duration_rounds": 2,
    },
    "Covet": {
        "name": "Covet",
        "description": "Steal a random card from another player, but your theft will be publicly announced in two rounds!",
        "phase_restriction": ["Evening"],
        "target_type": "other_player",
        "effect_type": "steal_card",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 0,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Immolation": {
        "name": "Immolation",
        "description": "Burn with a holy fire for two rounds, causing anyone who plays a card against you to burst into flames and die within two rounds! This does not protect against death by voting or by Cultists.",
        "phase_restriction": ["Evening"],
        "target_type": "self",
        "effect_type": "immolation",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 2,
        "dead_card": False,
        "duration_rounds": 3,
    },
    "Act of God": {
        "name": "Act of God",
        "description": "Conjure a storm and destroy a player's home, forcing them to lose all of their cards. The person who lost their cards will be announced in the Morning.",
        "phase_restriction": ["Evening"],
        "target_type": "other_player",
        "effect_type": "lose_all_cards",
        "is_public": True,
        "reveals_player": False,
        "sacrifice_cards": 1,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Feed the Maggots": {
        "name": "Feed the Maggots",
        "description": "Cause chaos after your death by forcing everyone to throw away their cards and receive two new cards. May be played after you have been killed by Cultists, voting, or any other means.",
        "phase_restriction": ["Any"],
        "target_type": "none",
        "effect_type": "feed_the_beast",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 0,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Screams from the Void": {
        "name": "Screams from the Void",
        "description": "The Dark God will whisper to you the name of someone (alive or dead) who is not a Cultist, but you are silenced, delirious, and unable to vote for one round.",
        "phase_restriction": ["Evening"],
        "target_type": "self",
        "effect_type": "screams_from_the_void",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 2,
        "dead_card": False,
        "duration_rounds": 1,
    },
    "False Idol": {
        "name": "False Idol",
        "description": "Pray to the Dark God and learn if at least one of the Dead is a Cultist. However, you cannot speak or use any cards for one full round. This card may also be played during an Apocalypse Vote to immediately cancel the vote and avert The Apocalypse.",
        "phase_restriction": ["Evening", "ApocalypseVote"],
        "target_type": "self",
        "effect_type": "false_idol",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 0,
        "dead_card": False,
        "duration_rounds": 1,
    },
    "Extended Delirium": {
        "name": "Extended Delirium",
        "description": "Induces prolonged insanity in another player, preventing them from playing any cards for the next two Evenings.",
        "phase_restriction": ["Evening"],
        "target_type": "other_player",
        "effect_type": "delirium",
        "is_public": True,
        "reveals_player": False,
        "sacrifice_cards": 1,
        "dead_card": False,
        "duration_rounds": 2,
    },
    "Silver Tongue": {
        "name": "Silver Tongue",
        "description": "Cast a second vote for a nominated player during execution voting. You may also vote once using this card if your voting has been restricted.",
        "phase_restriction": ["Voting"],
        "target_type": "self",
        "effect_type": "extra_vote",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 0,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Delirium": {
        "name": "Delirium",
        "description": "Induces temporary insanity in another player, preventing them from playing any cards the following Evening.",
        "phase_restriction": ["Evening"],
        "target_type": "other_player",
        "effect_type": "delirium",
        "is_public": True,
        "reveals_player": False,
        "sacrifice_cards": 1,
        "dead_card": False,
        "duration_rounds": 1,
    },
    "Silence": {
        "name": "Silence",
        "description": "Silence another player for one round. They cannot speak in person.",
        "phase_restriction": ["Evening", "Night"],
        "target_type": "other_player",
        "effect_type": "silence",
        "is_public": True,
        "reveals_player": False,
        "sacrifice_cards": 0,
        "dead_card": False,
        "duration_rounds": 1,
    },
    "The Apocalypse": {
        "name": "The Apocalypse",
        "description": "Force an immediate vote to reveal a player's role. If the vote fails, this triggers Carnage, allowing the Cultists to kill two players the following Night!",
        "phase_restriction": ["Evening"],
        "target_type": "other_player",
        "effect_type": "apocalypse_vote",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 1,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Paranoia": {
        "name": "Paranoia",
        "description": "Know if anything has been played against you during the Night phase in which it was played and the two following Night phases. Allows you to counter attacks and attempts by the Cultists to kill you!",
        "phase_restriction": ["Evening"],
        "target_type": "self",
        "effect_type": "paranoid",
        "is_public": False,
        "reveals_player": False,
        "sacrifice_cards": 0,
        "dead_card": False,
        "duration_rounds": 2,
    },
    "Cleansing Ritual": {
        "name": "Cleansing Ritual",
        "description": "Removes all negative status effects applied during the previous Night and prevents one kill attempt against you this Dawn.",
        "phase_restriction": ["Dawn"],
        "target_type": "self",
        "effect_type": "cleanse",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 1,
        "dead_card": False,
        "duration_rounds": 0,
    },
    "Holy Water": {
        "name": "Holy Water",
        "description": "All players remain alive for an entire Night and cures any poisons or afflictions in play. Play during the Evening.",
        "phase_restriction": ["Evening"],
        "target_type": "none",
        "effect_type": "protect_all_cure",
        "is_public": True,
        "reveals_player": False,
        "sacrifice_cards": 2,
        "dead_card": False,
        "duration_rounds": 1,
    },
    "Binding Rite": {
        "name": "Binding Rite",
        "description": "Bind the fates of two players (e.g. if one bound player is poisoned, the other bound player is also poisoned) for two rounds. You may bind yourself to another player. Both bound players will be announced in the Morning. Play during the Evening.",
        "phase_restriction": ["Evening"],
        "target_type": "two_players",
        "effect_type": "bind_fates",
        "is_public": True,
        "reveals_player": True,
        "sacrifice_cards": 0,
        "dead_card": False,
        "duration_rounds": 2,
    },
    "Ghostly Silence": {
        "name": "Ghostly Silence",
        "description": "Same as the normal \"Silence\" card, but 15% spookier.",
        "phase_restriction": ["Any"],
        "target_type": "other_player",
        "effect_type": "silence",
        "is_public": True,
        "reveals_player": False,
        "sacrifice_cards": 0,
        "dead_card": True,
        "duration_rounds": 1,
    },
    "Spectral Block": {
        "name": "Spectral Block",
        "description": "As a dead player, block an alive player from voting in the next Voting phase.",
        "phase_restriction": ["Evening", "Night"],
        "target_type": "other_player",
        "effect_type": "vote_block",
        "is_public": True,
        "reveals_player": False,
        "sacrifice_cards": 0,
        "dead_card": True,
        "duration_rounds": 1,
    },
}


class Card:
    def __init__(self, card_name):
        if card_name not in CARD_DEFINITIONS:
            raise ValueError(f"Card '{card_name}' not found in definitions.")
        self.id = str(uuid.uuid4())
        self.name = card_name
        self.definition = CARD_DEFINITIONS[card_name]
        self.description = self.definition["description"]
        self.phase_restriction = self.definition["phase_restriction"]
        self.target_type = self.definition["target_type"]
        self.effect_type = self.definition["effect_type"]
        self.is_public = self.definition["is_public"]
        self.reveals_player = self.definition["reveals_player"]
        self.sacrifice_cards = self.definition["sacrifice_cards"]
        self.dead_card = self.definition["dead_card"]
        self.duration_rounds = self.definition["duration_rounds"]

    def to_dict(self):
        card_data = self.definition.copy()
        card_data['id'] = self.id
        return card_data

    def __str__(self):
        return f"{self.name} ({self.id})"

    @staticmethod
    def from_dict(data):
        card = Card(data["name"])
        card.id = data.get("id", str(uuid.uuid4()))
        return card


class Deck:
    def __init__(self, is_dead_deck=False):
        self.cards = []
        for card_name, count in DECK_COMPOSITION.items():
            if card_name in CARD_DEFINITIONS:
                is_card_for_this_deck = CARD_DEFINITIONS[card_name]["dead_card"] == is_dead_deck
                if is_card_for_this_deck:
                    for _ in range(count):
                        self.cards.append(Card(card_name))
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self, num_cards):
        if len(self.cards) < num_cards:
            num_cards = len(self.cards)
        return [self.cards.pop() for _ in range(num_cards)]

    def add_cards(self, cards_to_add):
        self.cards.extend(cards_to_add)
        self.shuffle()


class Player:
    def __init__(self, player_id, name):
        self.player_id = player_id
        self.name = name
        self.score = 0
        self.contract = None
        self.role = None
        self.hand = []
        self.is_alive = True
        self.status_effects = {}
        self.has_voted = False
        self.has_submitted_evening_cards = False
        self.is_asleep = False
        self.voted_for = None
        self.nominated_players = []
        self.has_completed_dawn_action = False

    def add_card(self, card):
        self.hand.append(card)

    def remove_card_by_id(self, card_id):
        for i, card in enumerate(self.hand):
            if card.id == card_id:
                return self.hand.pop(i)
        return None

    def get_card_by_id(self, card_id):
        for card in self.hand:
            if card.id == card_id:
                return card
        return None

    def apply_status_effect(self, effect_type, duration_or_data):
        self.status_effects[effect_type] = duration_or_data
        print(f"{self.name} now has {effect_type} with data: {duration_or_data}.")

    def decrement_status_effects(self):
        effects_that_expired = []
        effects_to_remove = []
        for effect, data in self.status_effects.items():
            if isinstance(data, int):
                self.status_effects[effect] -= 1
                if self.status_effects[effect] <= 0:
                    effects_to_remove.append(effect)
        for effect in effects_to_remove:
            del self.status_effects[effect]
            effects_that_expired.append(effect)
            print(f"DEBUG: {self.name}'s '{effect}' effect has worn off.")
        return effects_that_expired

    def to_dict(self, include_hand=False):
        data = {
            "player_id": self.player_id,
            "name": self.name,
            "is_alive": self.is_alive,
            "status_effects": self.status_effects,
            "has_voted": self.has_voted,
            "has_submitted_evening_cards": self.has_submitted_evening_cards,
            "is_asleep": self.is_asleep,
            "has_completed_dawn_action": self.has_completed_dawn_action,
        }
        if include_hand:
            data["hand"] = [card.to_dict() for card in self.hand]
        return data

    @staticmethod
    def from_dict(data):
        player = Player(data["player_id"], data["name"])
        player.is_alive = data["is_alive"]
        player.status_effects = data["status_effects"]
        player.has_voted = data["has_voted"]
        player.has_submitted_evening_cards = data.get("has_submitted_evening_cards", False)
        player.is_asleep = data.get("is_asleep", False)
        player.has_completed_dawn_action = data.get("has_completed_dawn_action", False)
        if "hand" in data:
            player.hand = [Card.from_dict(c_data) for c_data in data["hand"]]
        return player


class GameState:
    def __init__(self):
        self.players = {}
        self.alive_players = []
        self.dead_players = []
        self.deck = Deck(is_dead_deck=False)
        self.dead_deck = Deck(is_dead_deck=True)
        self.current_phase = "Starting"
        self.round_number = 0
        self.global_status_effects = {}
        self.public_announcements = []
        self.lobby_ready_players = set() # ADDED: Track ready players in lobby
        self.death_log = []
        self.active_rituals = {}
        self.game_scores = {}

        self.evening_submitted_players = set()
        self.night_asleep_players = set()
        self.cultist_kill_votes = {}
        self.cultist_kill_target = None
        self.pending_night_actions = []
        self.delayed_actions = []
        self.dawn_active_players = set()
        self.dawn_completed_actions = set()

        self.morning_ready_players = set()

        self.voting_sub_phase = "Inactive"
        self.voting_nominations = {}
        self.nominated_speakers = []
        self.current_speaker_index = -1
        self.voters_ready_for_execution = set()
        self.voting_final_votes = {}
        self.voting_abstainers = set()

        self.apocalypse_vote_target = None
        self.apocalypse_votes = {}

        self.dusk_ready_players = set()

        self.last_phase_start_time = 0
        self.bound_players = {}

        self.desired_players_count = 0
        self.game_setup_completed = False

    def add_player(self, player_id, name):
        if player_id not in self.players:
            player = Player(player_id, name)
            self.players[player_id] = player
            self.alive_players.append(player_id)
            print(f"Player {name} ({player_id}) joined.")
            return True
        return False

    def get_player(self, player_id):
        return self.players.get(player_id)

    def get_player_by_name(self, player_name):
        for player in self.players.values():
            if player.name == player_name:
                return player
        return None

    def get_alive_player_names(self):
        return [self.players[pid].name for pid in self.alive_players]

    def get_dead_player_names(self):
        return [self.players[pid].name for pid in self.dead_players]

    def is_game_over(self):
        num_villagers_alive = sum(1 for pid in self.alive_players if self.players[pid].role == "Villager")
        num_cultists_alive = sum(1 for pid in self.alive_players if self.players[pid].role == "Cultist")

        if num_cultists_alive == 0:
            # --- START OF FIX ---
            # Check if a Doppelgänger is about to become a Cultist.
            # If so, the game is NOT over yet!
            pending_cultist_conversions = any(
                action['type'] == 'doppelganger_transform' and action['new_role'] == 'Cultist'
                for action in self.delayed_actions
            )
            
            if pending_cultist_conversions:
                print("[GAME_OVER_CHECK] Game over averted: A Doppelgänger is pending conversion to Cultist.")
                return False, None # The game is not over
            # --- END OF FIX ---
            message = "All Cultists have been eliminated!"
            
            # Find all dead cultists in the log
            cultist_deaths = [d for d in self.death_log if d['role'] == 'Cultist']
            
            death_summaries = []
            for death in cultist_deaths:
                # Clean up the 'source' text to be more readable
                source_text = death['source'].lower()
                if source_text in ['execution', 'voting']:
                    source_text = 'by voting'
                elif source_text == 'burning':
                    source_text = 'by burning'
                elif source_text == 'cultists':
                    source_text = 'by Cultists'
                elif source_text == 'harbinger of doom':
                    source_text = 'by the Harbinger of Doom'
                elif source_text == 'compulsion':
                    source_text = 'by a failed Compulsion'
                else:
                    source_text = f"by {death['source']}" # Default for other sources
                
                summary = f"Player {death['name']} was killed {source_text} during Round {death['round']}."
                death_summaries.append(summary)
            
            if death_summaries:
                message += " " + " ".join(death_summaries)
            
            message += " Villagers win!"
            #self.public_announcements.append(message)
            return True, "Villager"
        if num_villagers_alive <= num_cultists_alive:
            # --- START OF FIX ---
            message = "Cultists outnumber Villagers!"
            
            # Find all dead villagers in the log
            villager_deaths = [d for d in self.death_log if d['role'] == 'Villager']
            
            death_summaries = []
            for death in villager_deaths:
                # Clean up the 'source' text to be more readable
                source_text = death['source'].lower()
                if source_text in ['execution', 'voting']:
                    source_text = 'by voting'
                elif source_text == 'burning':
                    source_text = 'by burning'
                elif source_text == 'cultists':
                    source_text = 'by Cultists'
                elif source_text == 'harbinger of doom':
                    source_text = 'by the Harbinger of Doom'
                elif source_text == 'compulsion':
                    source_text = 'by a failed Compulsion'
                else:
                    source_text = f"by {death['source']}" # Default for other sources
                
                summary = f"Player {death['name']} was killed {source_text} during Round {death['round']}."
                death_summaries.append(summary)
            
            if death_summaries:
                message += " " + " ".join(death_summaries)
            
            message += " Cultists win!"
            #self.public_announcements.append(message)
            # --- END OF FIX ---
            return True, "Cultist"
# --- START OF FIX ---
        # If neither win condition was met, the game is not over.
        return False, None
        # --- END OF FIX ---

    def advance_phase(self):
        if self.current_phase != "Night" and self.current_phase != "GameOver" and self.current_phase != "Voting":
            self.public_announcements = []

        if self.current_phase == "Lobby":
            self.current_phase = "Evening"
            self.round_number = 0
        elif self.current_phase == "Evening":
            if self.apocalypse_vote_target:
                self.current_phase = "ApocalypseVote"
                self.last_phase_start_time = time.time()
            else:
                self.current_phase = "Night"
                self.public_announcements.append("Night has fallen. All players must now close their eyes and sleep. Once the bell tolls three times, the Cultists may open their eyes! Villagers may not open their eyes until they hear birds chirping.")
                
                # --- START OF FIX ---
                # The logic for decrementing status effects has been REMOVED from this file.
                # It is now handled correctly in server.py to prevent a double-decrement bug
                # and to allow the server to act immediately when an effect like 'burning' expires.
                # --- END OF FIX ---

                for pid in self.players: self.players[pid].is_asleep = False
                self.night_asleep_players.clear()
                self.cultist_kill_votes.clear()
                self.cultist_kill_target = None
        elif self.current_phase == "ApocalypseVote":
            self.current_phase = "Night"
            self.public_announcements.append("The vote is over. Night has fallen. All players must now close their eyes and sleep. Once the bell tolls three times, the Cultists may open their eyes! Villagers may not open their eyes until they hear birds chirping.")
            for pid in self.players:
                self.players[pid].decrement_status_effects()
            for pid in self.players: self.players[pid].is_asleep = False
            self.night_asleep_players.clear()
            self.cultist_kill_votes.clear()
            self.cultist_kill_target = None
        elif self.current_phase == "Night":
            self.current_phase = "Morning"
            self.round_number += 1
            self.morning_ready_players.clear()
            for pid in self.alive_players:
                player = self.players[pid]
                if player.is_alive:
                    new_card = self.deck.deal(1)
                    if new_card: player.add_card(new_card[0])
        elif self.current_phase == "Morning":
            self.current_phase = "Voting"
            self.voting_sub_phase = "Nomination"
            self.voting_nominations.clear()
            self.nominated_speakers.clear()
            self.current_speaker_index = -1
            self.voting_final_votes.clear()
            self.voters_ready_for_execution.clear()
            self.voting_abstainers.clear()
            for pid in self.alive_players: self.players[pid].has_voted = False
        elif self.current_phase == "Voting":
            self.current_phase = "Dusk"
            self.voting_sub_phase = "Inactive"
            self.public_announcements.append("The vote is over. You may now play any special cards before night falls.")
            self.dusk_ready_players.clear()
        elif self.current_phase == "Dusk":
            print(f"\n[PHASE_DEBUG] Advancing from Dusk to Evening (Sundown Occurring in Round {self.round_number})")
            for player in self.players.values():
                if 'divine_protection' in player.status_effects:
                    effect_data = player.status_effects['divine_protection']
                    if isinstance(effect_data, dict) and effect_data.get('applied_in_round', -1) < self.round_number:
                        del player.status_effects['divine_protection']
                        self.public_announcements.append(f"The divine protection on {player.name} has faded with the setting sun.")
                        print(f"[EFFECT] Divine Protection expired for {player.name} at the start of Evening, Round {self.round_number}")
            self.current_phase = "Evening"
            self.last_phase_start_time = time.time() 
            self.public_announcements.append("It is now Evening. Play your cards or click 'Confirm Cards' when you are done.")
            self.evening_submitted_players.clear()
            self.pending_night_actions.clear()
            for player in self.players.values():
                player.has_submitted_evening_cards = False

        game_over, winner = self.is_game_over()
        if game_over:
            self.current_phase = "GameOver"
            self.public_announcements.append(f"Game Over! {winner} win!")

    def get_public_game_state(self):
        # --- START OF FIX ---
        
        def get_safe_name(pid):
            """Helper to get player name or return a placeholder if player disconnected."""
            player = self.players.get(pid)
            return player.name if player else f"Player({pid[:4]})"

        cultist_votes_by_name = {
            get_safe_name(voter_id): get_safe_name(target_id)
            for voter_id, target_id in self.cultist_kill_votes.items()
            # No need for 'if in self.players' here, get_safe_name handles it
        }
        
        public_nominations = {}
        for nominator_id, nominated_ids in self.voting_nominations.items():
            nominator_name = get_safe_name(nominator_id)
            nominated_names = [get_safe_name(nid) for nid in nominated_ids]
            public_nominations[nominator_name] = nominated_names
        
        # Filter out disconnected players from these lists
        safe_nominated_speakers = [pid for pid in self.nominated_speakers if pid in self.players]
        
        current_speaker_name = None
        if (self.current_speaker_index != -1 and 
            safe_nominated_speakers and 
            self.current_speaker_index < len(safe_nominated_speakers)):
            speaker_id = safe_nominated_speakers[self.current_speaker_index]
            current_speaker_name = get_safe_name(speaker_id)

        safe_final_votes = {
            get_safe_name(voter_id): get_safe_name(target_id)
            for voter_id, target_id in self.voting_final_votes.items()
        }

        return {
            "current_phase": self.current_phase, "round_number": self.round_number, "global_status_effects": self.global_status_effects, "public_announcements": self.public_announcements,
            "lobby_ready_count": len(self.lobby_ready_players),
            "lobby_ready_players": list(self.lobby_ready_players),
            "evening_submitted_count": len(self.evening_submitted_players), "night_asleep_count": len(self.night_asleep_players), "morning_ready_count": len(self.morning_ready_players),
            "voting_sub_phase": self.voting_sub_phase, "voting_nominations": public_nominations, 
            "nominated_speakers": [get_safe_name(pid) for pid in safe_nominated_speakers],
            "current_speaker": current_speaker_name,
            "voters_ready_for_execution_count": len(self.voters_ready_for_execution), 
            "voting_final_votes": safe_final_votes,
            "voting_abstainers_count": len(self.voting_abstainers),
            "dusk_ready_count": len(self.dusk_ready_players), 
            "apocalypse_vote_target": get_safe_name(self.apocalypse_vote_target) if self.apocalypse_vote_target else None, 
            "apocalypse_votes": self.apocalypse_votes,
            "last_phase_start_time": self.last_phase_start_time, "dawn_active_players_count": len(self.dawn_active_players), "dawn_completed_actions_count": len(self.dawn_completed_actions),
            "cultist_kill_votes": cultist_votes_by_name, 
            "cultist_kill_target": get_safe_name(self.cultist_kill_target) if self.cultist_kill_target else None,
        }
        # --- END OF FIX ---
    def get_player_private_state(self, player_id):
        player = self.players[player_id]
        return {
            "player_id": player.player_id, "name": player.name, "role": player.role, "is_alive": player.is_alive, "hand": [card.to_dict() for card in player.hand], "status_effects": player.status_effects,
            "has_completed_dawn_action": player.has_completed_dawn_action, "is_dawn_active_player": player.player_id in self.dawn_active_players,
            "pending_night_actions_for_player": [ action for action in self.pending_night_actions if action["target_id"] == player_id and action["is_counterable"] ]
        }

# --- CONTRACTS ---

CONTRACT_DEFINITIONS = {
    "brothers_keeper": {
        "name": "Brother's Keeper",
        "description": "Select another player. If that player survives until the end of the game, earn an extra point. If that player dies, lose a point."
    },
    "lamb_of_god": {
        "name": "Lamb of God",
        "description": "As a peace-loving Villager, avoid any killing to earn an extra point. Lose one point if you cause anyone to die by voting or by playing Immolation and inflicting Burning, Harbinger of Doom and killing someone, Compulsion and killing a Cultist, or the Apocalypse and triggering Carnage.",
        "target_type": "self" # This tells the UI not to ask for a target
    },
    "thick_skinned": {
        "name": "Thick Skinned",
        "description": "Avoid dying at least 2 times to earn an extra point. You must be saved by a Hand of Glory, brought back to life using Resurrection Ritual, cleansed with I Saw the Light while you are Burning, or play False Idol to prevent the Apocalypse. Lazarus does not count. If you do not avoid dying at least twice, lose 1 point.",
        "target_type": "self"
    }
}