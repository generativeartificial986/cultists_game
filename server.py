# -*- coding: utf-8 -*-
"""Game Server (server.py) - Voting System Update"""
import os
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import time
from collections import defaultdict, Counter

from card_game import GameState, Card, Player, CARD_DEFINITIONS

# --- Flask & SocketIO Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Global Game State ---
game_state = None
clients = {}             # Maps SID -> player_id
player_name_to_id = {}   # Maps player name -> player_id

# --- Configuration Constants ---
INITIAL_HAND_SIZE = 3
# REMOVED: EVENING_TIMER_SECONDS is no longer needed
VOTING_NOMINATION_TIMER_SECONDS = 30
VOTING_SPEAKER_TIMER_SECONDS = 30
VOTING_EXECUTION_TIMER_SECONDS = 30
NIGHT_SLEEP_DELAY_SECONDS = 4
ANNOUNCEMENT_DELAY_SECONDS = 5 # How long to show vote results

def reset_game():
    """Resets the entire game state to its initial condition."""
    global game_state, clients, player_name_to_id
    game_state = GameState()
    game_state.desired_players_count = 0
    game_state.game_setup_completed = False
    game_state.current_phase = "Lobby"
    clients.clear()
    player_name_to_id.clear()
    print("[RESET] Game state reset to Lobby phase.")

# --- Socket.IO Event Handlers ---

@socketio.on('connect')
def handle_connect(auth):
    """Handles new client connections, with auth reuse of existing player_id."""
    sid = request.sid
    print(f"[CONNECT] SID={sid} auth={auth}")

    # 1) Reattach existing player if client sent valid player_id
    pid = None
    if auth:
        requested = auth.get('player_id')
        if requested and requested in game_state.players:
            pid = requested

    if pid:
        clients[sid] = pid
        join_room(sid)
        emit('initial_connect', {"player_id": pid}, room=sid)
        broadcast_game_state()
        return

    # 2) Observers during game
    if game_state.current_phase != "Lobby":
        if sid in clients:
            pid = clients[sid]
            join_room(sid)
            emit('initial_connect', {"player_id": pid}, room=sid)
            broadcast_game_state()
            return
        emit('game_in_progress',
             {"message": "Game already in progress. You are observing."},
             room=sid)
        return

    # 3) New lobby connection: create temp guest
    temp_id = f"temp_player_{sid}"
    if temp_id not in game_state.players:
        guest_num = 1 + sum(1 for p in game_state.players.values()
                            if p.name.startswith("Guest_"))
        game_state.add_player(temp_id, f"Guest_{guest_num}")
    clients[sid] = temp_id
    join_room(sid)
    print(f"[LOBBY] New temp player: {temp_id}")
    emit('initial_connect', {"player_id": temp_id}, room=sid)

    if game_state.desired_players_count == 0:
        emit('prompt_set_player_count', room=sid)
    else:
        emit('prompt_for_name', room=sid)

    broadcast_game_state()

@socketio.on('disconnect')
def handle_disconnect():
    """Handles client disconnection and cleans up."""
    sid = request.sid
    print(f"[DISCONNECT] SID={sid}")
    if sid not in clients:
        return

    pid = clients.pop(sid)
    player = game_state.get_player(pid)
    if player:
        print(f"[DISCONNECT] Removing player: {player.name} ({pid})")
        game_state.players.pop(pid, None)
        if pid in game_state.alive_players:
            game_state.alive_players.remove(pid)
        if pid in game_state.dead_players:
            game_state.dead_players.remove(pid)
        player_name_to_id.pop(player.name, None)

        game_state.lobby_ready_players.discard(pid)
        game_state.evening_submitted_players.discard(pid)
        game_state.night_asleep_players.discard(pid)
        game_state.cultist_kill_votes.pop(pid, None)
        game_state.dawn_active_players.discard(pid)
        game_state.dawn_completed_actions.discard(pid)
        game_state.morning_ready_players.discard(pid)
        game_state.voting_nominations.pop(pid, None)
        game_state.voting_final_votes.pop(pid, None)
        game_state.apocalypse_votes.pop(pid, None)
        game_state.dusk_ready_players.discard(pid)
        game_state.voters_ready_for_execution.discard(pid)


        bound = game_state.bound_players.pop(pid, None)
        if bound:
            game_state.bound_players.pop(bound, None)
            partner_name = (game_state.players[bound].name
                            if bound in game_state.players else "Unknown")
            game_state.public_announcements.append(
                f"{player.name}'s binding to {partner_name} broke due to disconnect."
            )

    broadcast_game_state()

@socketio.on('set_desired_player_count')
def handle_set_desired_player_count(data):
    """Handles host setting total number of players."""
    sid = request.sid
    if game_state.current_phase != "Lobby" or game_state.desired_players_count != 0:
        emit('error', {"message": "Cannot set player count now."}, room=sid)
        return

    count = int(data.get("count", 0))
    if count < 3:
        emit('error', {"message": "Please set a minimum of 3 players."}, room=sid)
        return

    game_state.desired_players_count = count
    print(f"[LOBBY] Desired player count set to: {count}")
    emit('prompt_for_name', room=sid)
    broadcast_game_state()

@socketio.on('player_name_submit')
def handle_player_name_submit(data):
    """Handles player submitting their name."""
    sid = request.sid
    old_id = clients.get(sid)
    if not old_id:
        return

    name = data.get("name", "").strip()
    if not name or name in player_name_to_id:
        emit('error', {"message": "Invalid or taken name."}, room=sid)
        return

    player = game_state.get_player(old_id)
    new_id = f"player_{name.replace(' ', '_')}"
    player.player_id = new_id
    player.name = name

    game_state.players[new_id] = game_state.players.pop(old_id)
    clients[sid] = new_id
    player_name_to_id[name] = new_id

    if old_id in game_state.alive_players:
        game_state.alive_players.remove(old_id)
        game_state.alive_players.append(new_id)
    if old_id in game_state.dead_players:
        game_state.dead_players.remove(old_id)
        game_state.dead_players.append(new_id)

    print(f"[LOBBY] {old_id} named as {name} ({new_id})")
    emit('name_accepted', {"name": name, "player_id": new_id}, room=sid)
    broadcast_game_state()

@socketio.on('start_game_request')
def handle_start_game_request(data=None):
    """MODIFIED: Handles a player clicking the 'Ready' button in the lobby."""
    sid = request.sid
    pid = clients.get(sid)
    player = game_state.get_player(pid)

    if not pid or not player or game_state.current_phase != "Lobby" or game_state.game_setup_completed:
        return

    game_state.lobby_ready_players.add(pid)
    print(f"[LOBBY] {player.name} is ready to start. ({len(game_state.lobby_ready_players)}/{game_state.desired_players_count})")

    broadcast_game_state() # Let everyone know the count has updated

    named_count = sum(1 for p in game_state.players.values() if not p.name.startswith("Guest_"))

    # Game starts only if the number of ready players matches the desired count
    if len(game_state.lobby_ready_players) == game_state.desired_players_count and named_count == game_state.desired_players_count:
        game_state.game_setup_completed = True
        print("[GAME] All players are ready. Starting game logic.")
        start_game_logic()

@socketio.on('submit_evening_cards')
def handle_submit_evening_cards(data):
    """Handles Evening phase card submissions."""
    sid = request.sid
    pid = clients.get(sid)
    player = game_state.get_player(pid)

    if not pid or not player: return

    if 'harbinger_quest' in player.status_effects:
        quest_data = player.status_effects['harbinger_quest']
        if game_state.round_number >= quest_data['execute_at_round']:
            emit('prompt_harbinger_kill', room=sid)
            return

    if game_state.current_phase not in ["Evening", "Dusk"]:
        emit('error', {"message": f"Cannot play cards in {game_state.current_phase} phase."}, room=sid)
        return

    if game_state.current_phase == "Evening" and player.has_submitted_evening_cards:
        return

    selected_card_ids = data.get("selected_card_ids", [])
    sacrifice_card_ids = data.get("sacrifice_card_ids", [])
    targets = data.get("card_targets", {})

    valid_cards = []
    for card_id in selected_card_ids:
        c = player.get_card_by_id(card_id)
        if not c: return
        if "delirium" in player.status_effects and c.name != "I Saw the Light":
            emit('error', {"message": "You are delirious and cannot play cards."}, room=sid)
            return
        if game_state.current_phase not in c.phase_restriction and "Any" not in c.phase_restriction:
            emit('error', {"message": f"Cannot play {c.name} now."}, room=sid)
            return
        valid_cards.append(c)

    for c in valid_cards:
        player.remove_card_by_id(c.id)

        actual_sacrifices = []
        for s_id in sacrifice_card_ids:
            s_card = player.get_card_by_id(s_id)
            if s_card:
                actual_sacrifices.append(s_card)

        if len(actual_sacrifices) < c.sacrifice_cards:
            emit('error', {"message": f"Not enough cards to sacrifice for {c.name}."}, room=sid)
            player.add_card(c) # Return the played card to hand
            for s_card in actual_sacrifices: # Return sacrifices to hand
                player.add_card(s_card)
            return

        for s_card in actual_sacrifices:
            player.remove_card_by_id(s_card.id)

        apply_card_effect(pid, c, targets.get(c.id))

    if game_state.current_phase == "Evening":
        player.has_submitted_evening_cards = True
        game_state.evening_submitted_players.add(pid)

    emit('action_confirmed', {"message": "Cards submitted!"}, room=sid)
    broadcast_game_state()

    connected_pids = set(clients.values())
    
    alive_and_connected = [pid for pid in game_state.alive_players if pid in connected_pids]
    dead_with_cards_and_connected = [pid for pid in game_state.dead_players if pid in connected_pids and game_state.players[pid].hand]
    
    expected_to_submit = alive_and_connected + dead_with_cards_and_connected

    print("\n[EVENING_DEBUG] Evening submission status:")
    submitted_names = {game_state.players[p_id].name for p_id in game_state.evening_submitted_players}
    expected_names = {game_state.players[p_id].name for p_id in expected_to_submit}
    waiting_for_names = expected_names - submitted_names
    
    print(f"[EVENING_DEBUG] Players who have submitted: {list(submitted_names) or 'None'}")
    print(f"[EVENING_DEBUG] Server is waiting for: {list(waiting_for_names) or 'Nobody'}")

    if game_state.current_phase == "Evening" and len(game_state.evening_submitted_players) >= len(expected_to_submit):
        print("[EVENING_DEBUG] All expected players have submitted. Handling end-of-evening effects.")
        
        # --- START OF FIX ---
        # The logic to check for burn deaths now lives here, on the server,
        # right before the phase advances.
        players_to_kill_from_burn = []
        for p_id, p_obj in game_state.players.items():
            if p_obj.is_alive:
                expired_effects = p_obj.decrement_status_effects()
                if 'burning' in expired_effects:
                    players_to_kill_from_burn.append((p_id, p_obj.name))
        
        for p_id, p_name in players_to_kill_from_burn:
            game_state.public_announcements.append(f"{p_name} has succumbed to their burns and died!")
            kill_player(p_id, "Burning")
        # --- END OF FIX ---

        game_state.advance_phase()
        broadcast_game_state()

@socketio.on('play_special_card')
def handle_play_special_card(data):
    sid = request.sid
    pid = clients.get(sid)
    player = game_state.get_player(pid)
    card_id = data.get('card_id')
    card = player.get_card_by_id(card_id)

    if not pid or not player or not card:
        return

    if card.name == "Feed the Maggots":
        if player.is_alive:
            emit('error', {"message": "You can only play this card after you have died."}, room=sid)
            return

        player.remove_card_by_id(card.id)
        apply_card_effect(pid, card)
        emit('action_confirmed', {"message": "You have fed the maggots!"}, room=sid)
        broadcast_game_state()

    elif card.name == "Lazarus":
        if player.is_alive:
            emit('error', {"message": "You can only play Lazarus when you are dead."}, room=sid)
            return

        player.remove_card_by_id(card.id)
        apply_card_effect(pid, card)
        emit('action_confirmed', {"message": "You have risen!"}, room=sid)
        broadcast_game_state()

@socketio.on('toggle_sleep')
def handle_toggle_sleep(data=None):
    """Toggle sleep/wake during Night."""
    sid = request.sid
    pid = clients.get(sid)
    if not pid or game_state.current_phase != "Night":
        emit('error', {"message": "Not Night phase."}, room=sid)
        return

    player = game_state.get_player(pid)
    player.is_asleep = not player.is_asleep
    if player.is_asleep:
        game_state.night_asleep_players.add(pid)
    else:
        game_state.night_asleep_players.discard(pid)

    broadcast_game_state()
    check_night_sleep_progress()

@socketio.on('compulsion_response')
def handle_compulsion_response(data):
    sid = request.sid
    pid = clients.get(sid)
    player = game_state.get_player(pid)
    if not player or 'compelled' not in player.status_effects:
        return

    success = data.get('success', False)
    player.status_effects.pop('compelled', None)

    if success:
        game_state.public_announcements.append("The compelled Cultist was spared!")
        print(f"[QUEST] Compelled cultist {player.name} reported success.")
    else:
        game_state.public_announcements.append("The compelled Cultist failed and they were killed for their trespasses.")
        print(f"[QUEST] Compelled cultist {player.name} reported failure and will be killed.")
        kill_player(pid, "Compulsion")

    wake_cultists_for_kill_vote()
    broadcast_game_state()


@socketio.on('cultist_kill_vote')
def handle_cultist_kill_vote(data):
    """Handles Cultist kill voting."""
    sid = request.sid
    pid = clients.get(sid)
    if not pid:
        return
    player = game_state.get_player(pid)
    if (game_state.current_phase == "Night" and
        player.role == "Cultist" and player.is_alive):
        target_name = data.get("target_player_name")
        tplayer = game_state.get_player_by_name(target_name)
        if not tplayer or not tplayer.is_alive:
            emit('error', {"message": "Invalid target."}, room=sid)
            return
        game_state.cultist_kill_votes[pid] = tplayer.player_id
        emit('action_confirmed', {"message": f"Voted to kill {target_name}."}, room=sid)
        check_cultist_kill_consensus()
        broadcast_game_state()
    else:
        emit('error', {"message": "Not allowed."}, room=sid)

@socketio.on('confirm_cultist_kill')
def handle_confirm_cultist_kill(data=None):
    """Handles the final confirmation from Cultists to kill their target."""
    sid = request.sid
    pid = clients.get(sid)
    if not pid: return

    player = game_state.get_player(pid)
    if not (game_state.current_phase == "Night" and player.role == "Cultist" and player.is_alive and game_state.cultist_kill_target):
        return

    target_id = game_state.cultist_kill_target
    cultist_killers = [killer_id for killer_id in game_state.cultist_kill_votes if game_state.cultist_kill_votes[killer_id] == target_id]


    for cultist_id in cultist_killers:
        cultist_player = game_state.get_player(cultist_id)
        if cultist_player and 'violent_delights_quest' in cultist_player.status_effects:
            quest_data = cultist_player.status_effects['violent_delights_quest']
            if not quest_data.get('completed'):
                quest_data['completed'] = True
                print(f"[QUEST] {cultist_player.name} completed Violent Delights via cult kill.")

    kill_action = {
        "target_id": target_id,
        "effect_type": "kill",
        "source_id": pid,
        "is_counterable": True,
        "is_countered": False,
        "effect_data": {"killers": cultist_killers}
    }
    game_state.pending_night_actions.append(kill_action)

    target_name = game_state.players[target_id].name
    print(f"[NIGHT] Cultists confirmed kill on {target_name}")

    if game_state.global_status_effects.get("Carnage"):
        game_state.public_announcements.append("Carnage is active! The Cultists choose another victim.")
        game_state.global_status_effects["Carnage"] = False
        game_state.cultist_kill_votes.clear()
        game_state.cultist_kill_target = None
        broadcast_game_state()
    else:
        game_state.cultist_kill_votes.clear()
        game_state.cultist_kill_target = None
        resolve_dawn_actions()
        game_state.advance_phase()
        broadcast_game_state()

@socketio.on('harbinger_kill')
def handle_harbinger_kill(data):
    """Handles the kill submission from Harbinger of Doom."""
    sid = request.sid
    pid = clients.get(sid)
    player = game_state.get_player(pid)

    if not player or 'harbinger_quest' not in player.status_effects:
        return

    # --- START OF FIX ---
    # Add a check to ensure it's the correct round to kill.
    quest_data = player.status_effects['harbinger_quest']
    if game_state.round_number < quest_data['execute_at_round']:
        emit('error', {"message": "It is not yet time to fulfill the prophecy."}, room=sid)
        return
    # --- END OF FIX ---

    target_name = data.get('target_name')
    target_player = game_state.get_player_by_name(target_name)

    if not target_player or not target_player.is_alive:
        emit('error', {"message": "Invalid target for Harbinger of Doom."}, room=sid)
        return

    game_state.public_announcements.append(f"The dark prophecy was fulfilled! {player.name}'s became the Harbinger of Doom and claimed the life of {target_player.name}!")
    kill_player(target_player.player_id, "Harbinger of Doom", [pid])
    
    player.status_effects.pop('harbinger_quest', None)
    
    player.has_submitted_evening_cards = True
    game_state.evening_submitted_players.add(pid)
    
    emit('action_confirmed', {"message": f"You have killed {target_name}!"}, room=sid)
    broadcast_game_state()

@socketio.on('proceed_to_voting')
def handle_proceed_to_voting(data=None):
    """Handles players ready in Morning."""
    sid = request.sid
    pid = clients.get(sid)
    if not pid or game_state.current_phase != "Morning":
        return

    player = game_state.get_player(pid)
    if player and player.is_alive:
        game_state.morning_ready_players.add(pid)
        emit('action_confirmed', {"message": "Ready for voting!"}, room=sid)
        broadcast_game_state()

        all_alive_and_ready = all(p_id in game_state.morning_ready_players for p_id in game_state.alive_players)
        if len(game_state.morning_ready_players) >= len(game_state.alive_players) and all_alive_and_ready:
            game_state.advance_phase()
            start_voting_phase()
            broadcast_game_state()

@socketio.on('apocalypse_vote_submit')
def handle_apocalypse_vote_submit(data):
    """Handles players submitting their vote for The Apocalypse."""
    sid = request.sid
    pid = clients.get(sid)
    if not pid or game_state.current_phase != "ApocalypseVote":
        return

    player = game_state.get_player(pid)
    if not player or not player.is_alive or pid == game_state.apocalypse_vote_target or pid in game_state.apocalypse_votes:
        return

    vote = data.get('vote')
    if vote not in ['Yes', 'No']:
        return

    game_state.apocalypse_votes[pid] = vote
    print(f"[APOCALYPSE] {player.name} voted {vote}.")

    eligible_voters = [p_id for p_id in game_state.alive_players if p_id != game_state.apocalypse_vote_target]

    if len(game_state.apocalypse_votes) >= len(eligible_voters):
        print("[APOCALYPSE] All eligible players have voted. Resolving...")
        resolve_apocalypse_vote()

    broadcast_game_state()

@socketio.on('nominate_player')
def handle_nominate_player(data):
    sid = request.sid
    pid = clients.get(sid)
    player = game_state.get_player(pid)
    if not player or game_state.current_phase != "Voting" or game_state.voting_sub_phase != "Nomination":
        return

    if 'vote_restriction' in player.status_effects:
        emit('error', {"message": "You cannot nominate due to Screams from the Void."}, room=sid)
        return

    target_names = data.get('targets', [])
    if len(target_names) > 2:
        emit('error', {"message": "You can nominate at most two players."}, room=sid)
        return

    target_ids = []
    for name in target_names:
        target_player = game_state.get_player_by_name(name)
        if target_player and target_player.is_alive and target_player.player_id != pid:
            target_ids.append(target_player.player_id)

    game_state.voting_nominations[pid] = target_ids
    print(f"[VOTE] {game_state.players[pid].name} nominated: {[game_state.players[tid].name for tid in target_ids]}")
    broadcast_game_state()

@socketio.on('ready_for_execution_vote')
def handle_ready_for_execution_vote(data=None):
    sid = request.sid
    pid = clients.get(sid)
    if not pid or game_state.current_phase != "Voting" or game_state.voting_sub_phase != "Speaking":
        return

    game_state.voters_ready_for_execution.add(pid)
    broadcast_game_state()

    if len(game_state.voters_ready_for_execution) >= len(game_state.alive_players):
        game_state.voting_sub_phase = "Execution"
        game_state.last_phase_start_time = time.time()
        game_state.public_announcements.append("All players are ready. Vote to execute one of the speakers.")
        broadcast_game_state()

@socketio.on('submit_execution_vote')
def handle_submit_execution_vote(data):
    sid = request.sid
    pid = clients.get(sid)
    if not pid or game_state.current_phase != "Voting" or game_state.voting_sub_phase != "Execution":
        return

    player = game_state.get_player(pid)
    is_blocked = 'vote_block' in player.status_effects
    can_bypass = 'extra_vote' in player.status_effects
    is_restricted = 'vote_restriction' in player.status_effects
    if not player or not player.is_alive or player.has_voted or (is_blocked and not can_bypass) or is_restricted:
        return

    target_name = data.get('target')
    target_player = game_state.get_player_by_name(target_name)
    if not target_player or target_player.player_id not in game_state.nominated_speakers:
        emit('error', {"message": "Invalid execution vote target."}, room=sid)
        return

    player.has_voted = True
    game_state.voting_final_votes[pid] = target_player.player_id
    broadcast_game_state()

    check_execution_vote_completion()

@socketio.on('abstain_execution_vote')
def handle_abstain_execution_vote(data=None):
    sid = request.sid
    pid = clients.get(sid)
    if not pid or game_state.current_phase != "Voting" or game_state.voting_sub_phase != "Execution":
        return

    player = game_state.get_player(pid)
    is_blocked = 'vote_block' in player.status_effects
    can_bypass = 'extra_vote' in player.status_effects
    is_restricted = 'vote_restriction' in player.status_effects
    if not player or not player.is_alive or player.has_voted or (is_blocked and not can_bypass) or is_restricted:
        return

    player.has_voted = True
    game_state.voting_abstainers.add(pid)
    broadcast_game_state()

    check_execution_vote_completion()

@socketio.on('ready_for_evening')
def handle_ready_for_evening(data=None):
    sid = request.sid
    pid = clients.get(sid)
    if not pid or game_state.current_phase != "Dusk":
        return

    game_state.dusk_ready_players.add(pid)
    broadcast_game_state()

    if len(game_state.dusk_ready_players) >= len(game_state.players):
        game_state.last_phase_start_time = time.time()
        game_state.advance_phase()
        broadcast_game_state()

@socketio.on('play_voting_card')
def handle_play_voting_card(data):
    sid = request.sid
    pid = clients.get(sid)
    
    player = game_state.get_player(pid)
    selected_ids = data.get('selected_card_ids', [])
    card_id = selected_ids[0] if selected_ids else None
    
    card = player.get_card_by_id(card_id)
    sacrifice_ids = data.get("sacrifice_card_ids", [])
    targets = data.get("card_targets", {})

    if not card or ("Voting" not in card.phase_restriction and "Any" not in card.phase_restriction):
        return

    if "delirium" in player.status_effects and card.name != "I Saw the Light":
        emit('error', {"message": "You are delirious and cannot play cards."}, room=sid)
        return

    player.remove_card_by_id(card.id)
    actual_sacrifices = []
    for s_id in sacrifice_ids:
        s_card = player.get_card_by_id(s_id)
        if s_card:
            actual_sacrifices.append(s_card)

    if len(actual_sacrifices) < card.sacrifice_cards:
        emit('error', {"message": f"Not enough cards to sacrifice for {card.name}."}, room=sid)
        player.add_card(card)
        for s_card in actual_sacrifices:
            player.add_card(s_card)
        return

    for s_card in actual_sacrifices:
        player.remove_card_by_id(s_card.id)

    apply_card_effect(pid, card, targets.get(card.id))
    emit('action_confirmed', {"message": f"Played {card.name}!"}, room=sid)
    broadcast_game_state()

@socketio.on('play_any_phase_card')
def handle_play_any_phase_card(data):
    sid = request.sid
    pid = clients.get(sid)
    
    player = game_state.get_player(pid)
    selected_ids = data.get('selected_card_ids', [])
    card_id = selected_ids[0] if selected_ids else None

    card = player.get_card_by_id(card_id) if player else None
    sacrifice_ids = data.get("sacrifice_card_ids", [])
    targets = data.get("card_targets", {})

    if not pid or not player or not card:
        return

    if game_state.current_phase not in card.phase_restriction and "Any" not in card.phase_restriction:
        emit('error', {"message": f"Cannot play {card.name} during the {game_state.current_phase} phase."}, room=sid)
        return

    if "delirium" in player.status_effects and card.name != "I Saw the Light":
        emit('error', {"message": "You are delirious and cannot play cards."}, room=sid)
        return

    player.remove_card_by_id(card.id)
    actual_sacrifices = []
    for s_id in sacrifice_ids:
        s_card = player.get_card_by_id(s_id)
        if s_card:
            actual_sacrifices.append(s_card)

    if len(actual_sacrifices) < card.sacrifice_cards:
        emit('error', {"message": f"Not enough cards to sacrifice for {card.name}."}, room=sid)
        player.add_card(card)
        for s_card in actual_sacrifices:
            player.add_card(s_card)
        return

    for s_card in actual_sacrifices:
        player.remove_card_by_id(s_card.id)

# --- ADD THIS NEW FUNCTION BELOW ---
@socketio.on('reset_game_request')
def handle_reset_game_request(data=None):
    """Handles a client request to reset the entire game."""
    sid = request.sid
    print(f"[RESET] Game reset triggered by user {sid}.")
    
    # 1. Call your existing reset function
    reset_game() 
    
    # 2. Tell all clients the game has reset so they can reload
    emit('game_has_reset', 
         {"message": "The game was reset by an admin. Reloading..."}, 
         broadcast=True)
# --- END OF NEW FUNCTION ---

# --- Game Logic Helpers ---

def assign_roles():
    """Assigns Cultist or Villager to each player."""
    pids = list(game_state.players.keys())
    random.shuffle(pids)
    n = len(pids)
    if n <= 4: ccount = 1
    elif n <= 8: ccount = 1
    elif n <= 13: ccount = 2
    else: ccount = 3
    for i, pid in enumerate(pids):
        role = "Cultist" if i < ccount else "Villager"
        game_state.players[pid].role = role
        print(f"[ROLE] {game_state.players[pid].name} -> {role}")

def deal_initial_hands():
    """Deals initial hand to all alive players."""
    for pid in game_state.alive_players:
        player = game_state.players[pid]
        
        # 1. Deal the random cards
        cards = game_state.deck.deal(INITIAL_HAND_SIZE)
        for c in cards: player.add_card(c)
        
        # 2. Add the Hand of Glory
        try:
            hand_of_glory_card = Card("Hand of Glory")
            player.add_card(hand_of_glory_card)
            print(f"[DEAL] {player.name} receives {len(cards)} cards + Hand of Glory")
        except ValueError as e:
            print(f"[DEAL_ERROR] Could not create Hand of Glory: {e}")

def broadcast_game_state():
    """Broadcasts public and private game state to all clients."""
    public = game_state.get_public_game_state()
    public["desired_players_count"] = game_state.desired_players_count
    public["game_setup_completed"] = game_state.game_setup_completed
    connected_pids = set(clients.values())
    public["alive_players"] = []
    for pid in game_state.alive_players:
        if pid in game_state.players and pid in connected_pids:
            p_dict = game_state.players[pid].to_dict()
            p_dict['has_readied_morning'] = pid in game_state.morning_ready_players
            p_dict['has_readied_dusk'] = pid in game_state.dusk_ready_players
            p_dict['is_ready_for_execution'] = pid in game_state.voters_ready_for_execution
            public["alive_players"].append(p_dict)
    public["dead_players"] = [ p.to_dict() for pid, p in game_state.players.items() if not p.is_alive and pid in connected_pids ]
    for sid, pid in clients.items():
        if pid in game_state.players:
            socketio.emit('game_state_update', public, room=sid)
            private = game_state.get_player_private_state(pid)
            private["is_asleep"] = game_state.players[pid].is_asleep
            socketio.emit('private_player_state', private, room=sid)

def start_game_logic():
    """Starts Evening 0, reveals roles and objectives."""
    game_state.current_phase = "Evening"
    game_state.last_phase_start_time = time.time()
    game_state.public_announcements.append("The game begins! It is Evening. Play your cards or click 'Confirm Cards' when you are done.")
    assign_roles()
    deal_initial_hands()
    broadcast_game_state()
    for sid, pid in clients.items():
        pl = game_state.get_player(pid)
        objective = ("Objective: Find and eliminate all of the Cultists." if pl.role == "Villager" else "Objective: Kill the Villagers. Ensure the Cultists outnumber the Villagers.")
        socketio.emit('reveal_role', {"role": pl.role, "objective": objective}, room=sid)

def check_night_sleep_progress():
    """After everyone sleeps, run special night quests then wake Cultists."""
    total = len(game_state.players)
    if len(game_state.night_asleep_players) != total:
        return

    socketio.sleep(NIGHT_SLEEP_DELAY_SECONDS)

    socketio.emit('play_tolling_bell')

    for pid in game_state.alive_players:
        player = game_state.get_player(pid)
        if player and 'compelled' in player.status_effects:
            quest_data = player.status_effects['compelled']
            if game_state.round_number == quest_data['resolve_at_round']:
                sid = next((s for s, p_id in clients.items() if p_id == pid), None)
                if sid:
                    print(f"[QUEST] Prompting {player.name} for Compulsion resolution.")
                    emit('prompt_compulsion_resolution', room=sid)
                    return

    for pid in game_state.alive_players:
        player = game_state.get_player(pid)
        if player and 'compelled' in player.status_effects:
            quest_data = player.status_effects['compelled']
            if game_state.round_number == quest_data['initiated_at_round']:
                living_cultist_ids = [p_id for p_id in game_state.alive_players if game_state.players[p_id].role == "Cultist"]
                for cultist_id in living_cultist_ids:
                    is_the_one = (cultist_id == pid)
                    sid = next((s for s, p_id in clients.items() if p_id == cultist_id), None)
                    if sid:
                        print(f"[QUEST] Sending Compulsion initial prompt to {game_state.players[cultist_id].name}, is_selected={is_the_one}")
                        emit('prompt_compulsion_initial', {'is_selected': is_the_one}, room=sid)
                break

    wake_cultists_for_kill_vote()

def wake_cultists_for_kill_vote():
    """Sends the wake-up call to living cultists."""
    print("[NIGHT] Waking cultists for kill vote.")
    for sid, pid in clients.items():
        pl = game_state.get_player(pid)
        if pl.role == "Cultist" and pl.is_alive:
            socketio.emit('cultist_wake_up', {"message": "Cultists, open your eyes!"}, room=sid)
        else:
            socketio.emit('sleep_prompt', {"message": "Stay asleep."}, room=sid)
    broadcast_game_state()


def check_cultist_kill_consensus():
    """Checks if all living cultists have voted for the same target."""
    living_cultist_ids = [ pid for pid in game_state.alive_players if game_state.players[pid].role == "Cultist" ]
    if not living_cultist_ids: return
    if len(game_state.cultist_kill_votes) < len(living_cultist_ids):
        game_state.cultist_kill_target = None
        return
    votes = list(game_state.cultist_kill_votes.values())
    if len(set(votes)) == 1:
        game_state.cultist_kill_target = votes[0]
        target_name = game_state.players[votes[0]].name
        print(f"[NIGHT] Cultist consensus reached to kill {target_name}")
    else:
        game_state.cultist_kill_target = None

def apply_card_effect(player_id, card_obj, target_list=None):
    """Applies the effect of a played card."""
    player = game_state.get_player(player_id)
    t1_name = target_list[0] if target_list else None
    t1_obj = game_state.get_player_by_name(t1_name) if t1_name else None

    if t1_obj and 'immolated' in t1_obj.status_effects and player_id != t1_obj.player_id:
        if not 'burning' in player.status_effects:
            # --- START OF FIX ---
            # The duration is now 3 to ensure it lasts for 2 full rounds.
            # The delayed_actions logic has been removed.
            player.apply_status_effect('burning', 2)
            game_state.public_announcements.append(f"{player.name} caught fire! They will die in two rounds unless saved.")
            print(f"[EFFECT] {player.name} caught fire from attacking {t1_obj.name}.")
            # --- END OF FIX ---

    print(f"[CARD_EFFECT] {player.name} playing {card_obj.name} with effect {card_obj.effect_type}")
    #... rest of the function continues    if target_list: print(f"[CARD_EFFECT] Targets: {target_list}")
    
    # --- ADD THIS NEW ELIF BLOCK ---
    if card_obj.effect_type == "hand_of_glory":
        # Apply a secret status effect. 
        # We don't add this to STATUS_UI_MAP in index.html, so it stays hidden.
        player.apply_status_effect("hand_of_glory_protection", 2)
        print(f"[EFFECT] {player.name} secretly used Hand of Glory.")

    if card_obj.effect_type == "mark_of_the_beast":
        player.apply_status_effect("mark_of_the_beast", card_obj.duration_rounds)
        game_state.public_announcements.append(f"{player.name} was marked by the Beast, causing those who kill them to be publicly announced the Morning after their death!")
        print(f"[CARD] {player.name} is now Marked by the Beast for {card_obj.duration_rounds} rounds.")
    elif card_obj.effect_type == "eternal_winter":
        if t1_obj and t1_obj.is_alive:
            t1_obj.apply_status_effect("eternal_winter", card_obj.duration_rounds)
            game_state.public_announcements.append(f"{player.name} has cursed {t1_obj.name}, who must now sing 'All I Want for Christmas Is You' until sundown!")
    elif card_obj.effect_type == "compulsion":
        living_cultist_ids = [pid for pid in game_state.alive_players if game_state.get_player(pid).role == "Cultist"]
        if living_cultist_ids:
            compelled_id = random.choice(living_cultist_ids)
            compelled_player = game_state.get_player(compelled_id)
            compelled_player.apply_status_effect("compelled", {
                "initiated_at_round": game_state.round_number,
                "resolve_at_round": game_state.round_number + 1
            })
            game_state.public_announcements.append("One of the Cultists has been compelled to say the word \"Cultist\" at least once before the next sundown. if they fail, they will be killed!")
            print(f"[QUEST] {player.name} played Compulsion. {compelled_player.name} was selected.")
        else:
            game_state.public_announcements.append(f"{player.name} played Compulsion, but no Cultists could be found.")
            print(f"[QUEST] {player.name} played Compulsion, but no living cultists exist.")
    elif card_obj.effect_type == "third_eye":
        player_sid = next((sid for sid, p_id in clients.items() if p_id == player_id), None)
        if player_sid:
            revealed_cards = []
            for other_pid in game_state.alive_players:
                if other_pid != player_id:
                    other_player = game_state.get_player(other_pid)
                    if other_player and other_player.hand:
                        random_card = random.choice(other_player.hand)
                        revealed_cards.append({
                            "player_name": other_player.name,
                            "card": random_card.to_dict()
                        })
            socketio.emit('show_third_eye_vision', {'vision': revealed_cards}, room=player_sid)
        game_state.public_announcements.append(f"{player.name} received a vision from the Dark God, revealing a single card from each player's hand!")
        print(f"[CARD] {player.name} played Third Eye.")
    elif card_obj.effect_type == "protect":
        if t1_obj:
            game_state.pending_night_actions.append({ "target_id": t1_obj.player_id, "effect_type": "protect", "source_id": player_id, "is_counterable": False, "is_countered": False, "effect_data": {"duration": card_obj.duration_rounds} })
            print(f"[CARD] {player.name} played Protection Charm on {t1_obj.name}")
    elif card_obj.effect_type == "silence":
        if t1_obj:
            effect_data = { "duration": card_obj.duration_rounds, "source_name": player.name, "target_name": t1_obj.name }
            action = { "target_id": t1_obj.player_id, "effect_type": "silence", "source_id": player_id, "is_counterable": True, "is_countered": False, "effect_data": effect_data }
            game_state.pending_night_actions.append(action)
            print(f"[CARD] {player.name} played Silence on {t1_obj.name}")
    elif card_obj.effect_type == "apocalypse_vote":
        if t1_obj and t1_obj.is_alive:
            game_state.apocalypse_vote_target = t1_obj.player_id
            game_state.public_announcements.append(f"{player.name} played The Apocalypse! All players must now vote on whether to reveal {t1_obj.name}'s role.")
    elif card_obj.effect_type == "delirium":
        if t1_obj:
            effect_data = { "duration": card_obj.duration_rounds, "target_name": t1_obj.name }
            game_state.pending_night_actions.append({ "target_id": t1_obj.player_id, "effect_type": "delirium", "source_id": player_id, "is_counterable": True, "is_countered": False, "effect_data": effect_data })
            print(f"[CARD] {player.name} played Delirium on {t1_obj.name}")
    elif card_obj.effect_type == "extra_vote":
        player.apply_status_effect("extra_vote", 1)
        if 'vote_block' in player.status_effects or 'vote_restriction' in player.status_effects:
            game_state.public_announcements.append(f"{player.name} played Silver Tongue, allowing them to vote despite their voting restriction!")
        else:
            game_state.public_announcements.append(f"{player.name} played Silver Tongue, allowing them to cast two votes for the same player!")
    elif card_obj.effect_type == "false_idol":
        player_sid = next((sid for sid, p_id in clients.items() if p_id == player_id), None)
        if not player_sid: return

        cultist_found = any(game_state.get_player(dead_pid).role == "Cultist" for dead_pid in game_state.dead_players)

        if cultist_found:
            message = "The Dark God reveals to you that one of the Dead IS a Cultist!"
        else:
            message = "The Dark God reveals to you that none of the Dead is a Cultist."
        socketio.emit('private_announcement', {"message": message}, room=player_sid)

        # Defer the status effects until the start of Morning.
        action = {
            "target_id": player_id,
            "effect_type": "apply_false_idol_debuffs",
            "source_id": player_id,
            "is_counterable": True,
            "is_countered": False,
            "effect_data": {"duration": card_obj.duration_rounds}
        }
        game_state.pending_night_actions.append(action)
        print(f"[CARD] {player.name} played False Idol. Effects are pending for Morning.")

        game_state.public_announcements.append(f"{player.name} has prayed to a False Idol!")
    elif card_obj.effect_type == "screams_from_the_void":
        player_sid = next((sid for sid, p_id in clients.items() if p_id == player_id), None)
        if not player_sid: return

        non_cultist_ids = [pid for pid, p in game_state.players.items() if p.role != 'Cultist' and pid != player_id]
        if non_cultist_ids:
            revealed_id = random.choice(non_cultist_ids)
            revealed_name = game_state.players[revealed_id].name
            message = f"The Dark God whispers a name to you... {revealed_name} is not a Cultist."
            socketio.emit('private_announcement', {"message": message}, room=player_sid)
        else:
            message = "The Dark God finds no one worthy of its whispers."
            socketio.emit('private_announcement', {"message": message}, room=player_sid)

        # Defer the status effects until the start of Morning.
        action = {
            "target_id": player_id,
            "effect_type": "apply_screams_from_the_void_debuffs",
            "source_id": player_id,
            "is_counterable": True,
            "is_countered": False,
            "effect_data": {"duration": card_obj.duration_rounds}
        }
        game_state.pending_night_actions.append(action)
        print(f"[CARD] {player.name} played Screams from the Void. Effects are pending for Morning.")

        game_state.public_announcements.append(f"{player.name} prays to the Dark God, and is driven mad by what they hear. They have learned the name of one player who is not a Cultist.")
    elif card_obj.effect_type == "feed_the_beast":
        game_state.public_announcements.append(f"After dying, {player.name} decided to feed the maggots, causing all players to lose their cards!")
        for alive_pid in game_state.alive_players:
            alive_player = game_state.get_player(alive_pid)
            if alive_player:
                alive_player.hand.clear()
                new_cards = game_state.deck.deal(2)
                for new_card in new_cards:
                    alive_player.add_card(new_card)
        print(f"[CARD] {player.name} played Feed the Maggots. All hands reset.")
    elif card_obj.effect_type == "lose_all_cards":
        if t1_obj:
            action = {
                "target_id": t1_obj.player_id,
                "effect_type": "lose_all_cards",
                "source_id": player_id,
                "is_counterable": True,
                "is_countered": False,
                "effect_data": {"target_name": t1_obj.name}
            }
            game_state.pending_night_actions.append(action)
            print(f"[CARD] {player.name} played Act of God on {t1_obj.name}. Effect is pending for Morning.")
    elif card_obj.effect_type == "immolation":
        player.apply_status_effect("immolated", card_obj.duration_rounds)
        game_state.public_announcements.append(f"{player.name} burns with a holy fire! Anyone who plays a card against them will burst into flames, killing them within two rounds!")
        print(f"[CARD] {player.name} is now immolated for {card_obj.duration_rounds} rounds.")
    elif card_obj.effect_type == "steal_card":
        game_state.public_announcements.append(f"There are reports of a covetous thief in the area...")
        if t1_obj:
            game_state.delayed_actions.append({
                'type': 'steal_card_transfer',
                'thief_id': player_id,
                'victim_id': t1_obj.player_id,
                'execute_at_round': game_state.round_number + 1
            })
            game_state.delayed_actions.append({
                'type': 'reveal_thief',
                'thief_name': player.name,
                'victim_name': t1_obj.name,
                'execute_at_round': game_state.round_number + 2
            })
            print(f"[CARD] {player.name} played Covet on {t1_obj.name}. Effects are scheduled.")
    elif card_obj.effect_type == "violent_delights":
        quest_data = {
            'expires_at_round': game_state.round_number + 2,
            'completed': False
        }
        player.apply_status_effect("violent_delights_quest", quest_data)
        print(f"[QUEST] {player.name} started Violent Delights quest, expires at round {quest_data['expires_at_round']}.")
    elif card_obj.effect_type == "i_saw_the_light":
        if t1_obj:
            effects_to_cleanse = ['silence', 'delirium', 'burning', 'vote_restriction', 'violent_delights_quest']
            cleansed_an_effect = False

            for effect in effects_to_cleanse:
                if effect in t1_obj.status_effects:
                    t1_obj.status_effects.pop(effect, None)
                    cleansed_an_effect = True
                    print(f"[EFFECT] Cleansed {effect} from {t1_obj.name}")

            if 'burning' in effects_to_cleanse and cleansed_an_effect:
                game_state.delayed_actions = [
                    action for action in game_state.delayed_actions
                    if not (action['type'] == 'burn_death' and action['target_id'] == t1_obj.player_id)
                ]

            t1_obj.apply_status_effect("divine_protection", {'applied_in_round': game_state.round_number})

            if cleansed_an_effect:
                 game_state.public_announcements.append(f"{t1_obj.name} has been cleansed by a holy light!")
            else:
                 game_state.public_announcements.append(f"{t1_obj.name} is now divinely protected!")
            print(f"[CARD] {player.name} played I Saw the Light on {t1_obj.name}.")
    elif card_obj.effect_type == "peeping_tom":
        if t1_obj:
            player_sid = next((sid for sid, p_id in clients.items() if p_id == player_id), None)
            if player_sid:
                target_hand = [card.to_dict() for card in t1_obj.hand]
                socketio.emit('show_player_hand', {'player_name': t1_obj.name, 'hand': target_hand}, room=player_sid)

            game_state.delayed_actions.append({
                'type': 'peeping_tom_reveal',
                'peeper_name': player.name,
                'victim_name': t1_obj.name,
                'execute_at_round': game_state.round_number + 1
            })
            print(f"[CARD] {player.name} played Peeping Tom on {t1_obj.name}.")
    elif card_obj.effect_type == "lazarus":
        player.is_alive = True
        if player_id in game_state.dead_players:
            game_state.dead_players.remove(player_id)
        if player_id not in game_state.alive_players:
            game_state.alive_players.append(player_id)

        player.apply_status_effect("silence", 1)
        player.apply_status_effect("delirium", 1)
        player.apply_status_effect("lazarus_effect", {'expires_at_round': game_state.round_number})

        game_state.public_announcements.append(f"{player.name} was resurrected by the Dark God to participate in voting for one more round, but cannot speak or play any cards.")
        print(f"[CARD] {player.name} played Lazarus and is temporarily resurrected.")
    elif card_obj.effect_type == "harbinger_of_doom":
        quest_data = {
            'execute_at_round': game_state.round_number + 3
        }
        player.apply_status_effect("harbinger_quest", quest_data)
        game_state.public_announcements.append(f"{player.name} has performed a dark ritual, becoming a Harbinger of Doom! In three rounds, they will choose a victim to be sacrificed.")
        print(f"[QUEST] {player.name} started Harbinger of Doom. Kill will be available in round {quest_data['execute_at_round']}.")


def resolve_dawn_actions():
    """Resolves pending night actions immediately - called by server before phase transition."""
    print("[DAWN] Processing pending night actions...")

    for action in list(game_state.pending_night_actions):
        target_player = game_state.get_player(action['target_id'])
        if not target_player: continue
        if not action.get("is_countered", False):
            if action["effect_type"] == "kill":
                if "hand_of_glory_protection" in target_player.status_effects:
                    # Show your specific message
                    game_state.public_announcements.append(f"Cultists attempted to kill {target_player.name} last night, but they were saved by the glow of the Hand of Glory!")
                    # Remove the effect so it's one-time use
                    target_player.status_effects.pop("hand_of_glory_protection", None)
                    print(f"[EFFECT] {target_player.name} was saved by Hand of Glory.")
                elif "protected" in target_player.status_effects or "divine_protection" in target_player.status_effects:
                    game_state.public_announcements.append(f"{target_player.name} was protected from death!")
                else:
                    game_state.public_announcements.append(f"{target_player.name} was killed last night!");
                    kill_player(action['target_id'], "Cultists", action['effect_data'].get("killers", []))

    actions_to_remove = []
    for action in game_state.delayed_actions:
        if action['execute_at_round'] == game_state.round_number:
            if action['type'] == 'burn_death':
                target_player = game_state.get_player(action['target_id'])
                if target_player and target_player.is_alive:
                    game_state.public_announcements.append(f"{target_player.name} burned to death!")
                    kill_player(action['target_id'], "Immolation", [action['source_id']])
                actions_to_remove.append(action)
            elif action['type'] == 'steal_card_transfer':
                thief = game_state.get_player(action['thief_id'])
                victim = game_state.get_player(action['victim_id'])
                if thief and victim and victim.is_alive and victim.hand:
                    stolen_card = random.choice(victim.hand)
                    victim.remove_card_by_id(stolen_card.id) # FIXED: Use remove_card_by_id
                    thief.add_card(stolen_card)
                    # This announcement is now handled immediately when the card is played
                else:
                    print(f"[EFFECT] Covet steal failed. Victim {action['victim_id']} is dead or has no cards.")
                actions_to_remove.append(action)
            elif action['type'] == 'reveal_thief':
                game_state.public_announcements.append(f"After an investigation, it was discovered that {action['thief_name']} was the thief from two days ago!")
                print(f"[EFFECT] {action['thief_name']} was revealed as the thief.")
                actions_to_remove.append(action)

    for action in actions_to_remove:
        game_state.delayed_actions.remove(action)

    for player_id in list(game_state.players.keys()):
        player = game_state.get_player(player_id)
        if player and 'violent_delights_quest' in player.status_effects:
            quest_data = player.status_effects['violent_delights_quest']
            if quest_data.get('completed'):
                game_state.public_announcements.append(f"{player.name} delighted in their own violence, earning them two additional cards for their deviancy!")
                new_cards = game_state.deck.deal(2)
                for card in new_cards:
                    player.add_card(card)
                print(f"[QUEST] {player.name} succeeded Violent Delights, gets 2 cards.")
                player.status_effects.pop('violent_delights_quest', None)
            elif game_state.round_number > quest_data['expires_at_round']:
                game_state.public_announcements.append(f"{player.name} did not delight in their own violence, causing them to lose two cards! Guess they just didn't have the stomach for it.")
                if len(player.hand) > 0:
                    random.shuffle(player.hand)
                    player.hand.pop()
                if len(player.hand) > 0:
                    player.hand.pop()
                print(f"[QUEST] {player.name} failed Violent Delights, loses 2 cards.")
                player.status_effects.pop('violent_delights_quest', None)


    for player in game_state.players.values(): player.is_asleep = False
    game_state.night_asleep_players.clear()
    for action in list(game_state.pending_night_actions):
        target_player = game_state.get_player(action['target_id'])
        if not target_player: continue
        if not action.get("is_countered", False):
            if action["effect_type"] == "silence":
                duration, source_name, target_name = action["effect_data"].get("duration", 1), action["effect_data"].get("source_name", "Someone"), action["effect_data"].get("target_name", "a player")
                target_player.apply_status_effect("silence", duration); game_state.public_announcements.append(f"{target_name} has been silenced by {source_name}!")
            elif action["effect_type"] == "apply_screams_from_the_void_debuffs":
                duration = action["effect_data"].get("duration", 1)
                target_player.apply_status_effect("silence", duration)
                target_player.apply_status_effect("delirium", duration)
                target_player.apply_status_effect("vote_restriction", duration)
                game_state.public_announcements.append(f"The curse from Screams from the Void has taken hold of {target_player.name}!")
                print(f"[EFFECT] Applied Screams from the Void debuffs to {target_player.name}.")
            elif action["effect_type"] == "apply_false_idol_debuffs":
                duration = action["effect_data"].get("duration", 1)
                target_player.apply_status_effect("silence", duration)
                target_player.apply_status_effect("delirium", duration)
                game_state.public_announcements.append(f"The curse from the False Idol has taken hold of {target_player.name}!")
                print(f"[EFFECT] Applied False Idol debuffs to {target_player.name}.")
            elif action["effect_type"] == "protect":
                target_player.apply_status_effect("protected", action["effect_data"].get("duration", 1))
            elif action["effect_type"] == "delirium":
                duration, target_name = action["effect_data"].get("duration", 1), action["effect_data"].get("target_name", "A player")
                target_player.apply_status_effect("delirium", duration); game_state.public_announcements.append(f"{target_name} was made delirious!")
            elif action["effect_type"] == "lose_all_cards":
                target_name = action["effect_data"].get("target_name", "A player")
                target_player.hand.clear()
                game_state.public_announcements.append(f"{target_name} came back late to find their home in flames, losing all of their cards! The culprit has yet to be found...")
                print(f"[EFFECT] {target_name}'s hand was cleared by Pyromania.")
        else:
            game_state.public_announcements.append(f"{target_player.name} countered a {action['effect_type']} attempt!")
    game_state.pending_night_actions.clear()
def kill_player(player_id, source, killers=[]):
    """Kills a player and handles Mark of the Beast."""
    pl = game_state.get_player(player_id)
    if pl and pl.is_alive:
        if 'mark_of_the_beast' in pl.status_effects:
            killer_names = [game_state.players[kid].name for kid in killers if kid in game_state.players]
            if killer_names:
                game_state.public_announcements.append(f"The following players murdered the marked player, {pl.name}: {', '.join(killer_names)}")
                print(f"[MARK] Mark of the Beast revealed killers of {pl.name}: {', '.join(killer_names)}")
            pl.status_effects.pop('mark_of_the_beast', None)

        if 'compelled' in pl.status_effects:
            pl.status_effects.pop('compelled', None)
            print(f"[QUEST] Compelled player {pl.name} was killed, ending the quest.")

        # --- START OF FIX ---
        # Check if the dying player was the Harbinger of Doom.
        if 'harbinger_quest' in pl.status_effects:
            # Remove the status effect to cancel the quest.
            pl.status_effects.pop('harbinger_quest', None)
            # Add the special announcement. The generic death message will be on its own line.
            game_state.public_announcements.append("Their death caused the ritual for Harbinger of Doom to be interrupted.")
            print(f"[QUEST] {pl.name}'s death interrupted their Harbinger of Doom quest.")
        # --- END OF FIX ---

        cards_to_keep = [card for card in pl.hand if card.name in ["Feed the Maggots", "Lazarus"]]
        pl.hand.clear()
        for card in cards_to_keep:
            pl.add_card(card)

        pl.is_alive = False
        if player_id in game_state.alive_players: game_state.alive_players.remove(player_id)
        game_state.dead_players.append(player_id)

        print(f"[HAND_DEBUG] Dealing 3 dead cards to {pl.name} ({pl.player_id}).")
        newly_dealt_cards = game_state.dead_deck.deal(3)
        for c in newly_dealt_cards:
            pl.add_card(c)
        card_ids_in_hand = [card.id for card in pl.hand]
        print(f"[HAND_DEBUG] {pl.name}'s server-side hand now contains cards with these IDs: {card_ids_in_hand}")

        over, _ = game_state.is_game_over()
        if over: game_state.current_phase = "GameOver"; broadcast_game_state()

def resolve_apocalypse_vote():
    """Resolves the vote for The Apocalypse, reveals role or triggers Carnage."""
    if not game_state.apocalypse_vote_target: return
    target_player = game_state.get_player(game_state.apocalypse_vote_target)
    votes = game_state.apocalypse_votes.values()
    yes_votes = sum(1 for v in votes if v == 'Yes')
    no_votes = len(votes) - yes_votes
    announcement_message = ""
    if yes_votes > no_votes:
        announcement_message = f"The vote succeeded! {target_player.name}'s role has been revealed: they are a {target_player.role}!"
    else:
        announcement_message = f"The vote failed! Carnage will now start, allowing the Cultists to kill two players tonight!"
        game_state.global_status_effects["Carnage"] = True
    game_state.apocalypse_vote_target = None; game_state.apocalypse_votes.clear(); game_state.advance_phase()
    if announcement_message: game_state.public_announcements.append(announcement_message)

def start_voting_phase():
    """Initializes the nomination sub-phase of voting."""
    game_state.voting_sub_phase = "Nomination"
    game_state.last_phase_start_time = time.time()
    game_state.public_announcements.append("Nomination has begun! You have 30 seconds to nominate up to two players.")
    print("[VOTE] Nomination phase started.")

def process_nominations():
    """Processes nominations and determines who moves to the speaking phase."""
    all_nominations = [nid for sublist in game_state.voting_nominations.values() for nid in sublist]
    nomination_counts = Counter(all_nominations)
    game_state.nominated_speakers = [pid for pid, count in nomination_counts.items() if count >= 2]
    random.shuffle(game_state.nominated_speakers)
    if not game_state.nominated_speakers:
        game_state.public_announcements.append("No player received enough nominations. The day ends peacefully.")
        game_state.advance_phase()
        print("[VOTE] No speakers, advancing to Dusk.")
    else:
        speaker_names = [game_state.players[pid].name for pid in game_state.nominated_speakers]
        game_state.public_announcements.append(f"The following players have been nominated to speak: {', '.join(speaker_names)}")
        game_state.voting_sub_phase = "Speaking"
        game_state.current_speaker_index = 0
        print(f"[VOTE] Speakers are: {speaker_names}")
        start_next_speaker_turn()
    broadcast_game_state()

def start_next_speaker_turn():
    """Starts the timer for the current speaker."""
    if game_state.current_speaker_index < len(game_state.nominated_speakers):
        speaker_id = game_state.nominated_speakers[game_state.current_speaker_index]
        speaker_name = game_state.players[speaker_id].name
        game_state.public_announcements.append(f"It is now {speaker_name}'s turn to speak for 30 seconds.")
        game_state.last_phase_start_time = time.time()
        print(f"[VOTE] Speaker {speaker_name} starts their turn.")
        broadcast_game_state()
    else:
        game_state.public_announcements.append("All speakers have finished. Ready up to proceed to the execution vote.")
        game_state.current_speaker_index = -1 # Signal that speaking is done
        print("[VOTE] All speakers finished.")
        broadcast_game_state()

def check_execution_vote_completion():
    """Checks if all players have voted or abstained."""
    voted_count = len(game_state.voting_final_votes)
    abstained_count = len(game_state.voting_abstainers)
    if (voted_count + abstained_count) >= len(game_state.alive_players):
        resolve_execution_vote()
        game_state.advance_phase()
        broadcast_game_state()

def resolve_execution_vote():
    """Counts final votes and executes the player with the most."""
    final_votes_list = []
    voters_for_target = defaultdict(list)
    for voter_id, target_id in game_state.voting_final_votes.items():
        voter = game_state.get_player(voter_id)
        is_blocked = 'vote_block' in voter.status_effects or 'vote_restriction' in voter.status_effects
        can_bypass = 'extra_vote' in voter.status_effects

        if is_blocked and can_bypass:
            # --- START of Silver Tongue Edit 1 ---
            print(f"[VOTE_DEBUG] {voter.name} used Silver Tongue to bypass a vote restriction.")
            game_state.public_announcements.append(f"{voter.name} used Silver Tongue to bypass a voting restriction!")
            # --- END of Silver Tongue Edit 1 ---
            final_votes_list.append(target_id)
            voters_for_target[target_id].append(voter_id)
        elif not is_blocked and can_bypass:
            # --- START of Silver Tongue Edit 2 ---
            print(f"[VOTE_DEBUG] {voter.name} used Silver Tongue to cast a double vote.")
            game_state.public_announcements.append(f"{voter.name} used Silver Tongue to cast a second vote!")
            # --- END of Silver Tongue Edit 2 ---
            final_votes_list.extend([target_id, target_id])
            voters_for_target[target_id].append(voter_id)
        elif not is_blocked:
            final_votes_list.append(target_id)
            voters_for_target[target_id].append(voter_id)

        if can_bypass:
            voter.status_effects.pop('extra_vote', None)

    if not final_votes_list:
        game_state.public_announcements.append("No votes were cast. No one is executed.")
        return

    vote_counts = Counter(final_votes_list)
    most_votes = vote_counts.most_common(1)[0][1]
    tied_players = [pid for pid, count in vote_counts.items() if count == most_votes]
    if len(tied_players) > 1:
        tied_names = [game_state.players[pid].name for pid in tied_players]
        game_state.public_announcements.append(f"The vote was a tie between {', '.join(tied_names)}. No one is executed.")
        print("[VOTE] Execution vote tied. No one dies.")
    else:
        executed_id = tied_players[0]
        executed_player = game_state.get_player(executed_id)
        executed_name = executed_player.name

        if 'divine_protection' in executed_player.status_effects:
            executed_player.status_effects.pop('divine_protection', None)
            game_state.public_announcements.append(f"{executed_name} was voted to die, but by the grace of the Light, they were saved!")
            print(f"[EFFECT] {executed_name} was saved from execution by divine protection.")
        else:
            killers = voters_for_target.get(executed_id, [])
            for voter_id in killers:
                voter_player = game_state.get_player(voter_id)
                if voter_player and 'violent_delights_quest' in voter_player.status_effects:
                    quest_data = voter_player.status_effects['violent_delights_quest']
                    if not quest_data.get('completed'):
                        quest_data['completed'] = True
                        print(f"[QUEST] {voter_player.name} completed Violent Delights via execution vote.")

            game_state.public_announcements.append(f"By popular vote, {executed_name} has been executed!")
            print(f"[VOTE] {executed_name} is executed.")
            kill_player(executed_id, "Execution", killers)
    
    # --- START of Vote Totals Edit ---
    print("[VOTE_DEBUG] --- Execution Vote Summary ---")
    # Using a helper to safely get names for disconnected players
    def get_safe_name(p_id):
        return game_state.players[p_id].name if p_id in game_state.players else f"UnknownPlayer({p_id[:4]})"

    if game_state.voting_final_votes:
        for voter_id, target_id in game_state.voting_final_votes.items():
            print(f"[VOTE_DEBUG]   - {get_safe_name(voter_id)} voted for {get_safe_name(target_id)}")
    else:
        print("[VOTE_DEBUG]   - No players cast a vote.")
        
    if game_state.voting_abstainers:
        for abstainer_id in game_state.voting_abstainers:
            print(f"[VOTE_DEBUG]   - {get_safe_name(abstainer_id)} abstained.")
            
    print("[VOTE_DEBUG] Final Vote Tally:")
    if vote_counts:
        for target_id, count in vote_counts.items():
            print(f"[VOTE_DEBUG]   - {get_safe_name(target_id)}: {count} vote(s)")
    else:
        print("[VOTE_DEBUG]   - No votes were tallied.")
    print("[VOTE_DEBUG] --------------------------")
    # --- END of Vote Totals Edit ---

def game_loop():
    """Background loop for timers & auto transitions."""
    while True:
        socketio.sleep(0.5)
        if not game_state or not game_state.game_setup_completed: continue

        if game_state.current_phase == "Dusk":
            for player_id in list(game_state.alive_players):
                player = game_state.get_player(player_id)
                if player and 'lazarus_effect' in player.status_effects:
                    quest_data = player.status_effects['lazarus_effect']
                    if game_state.round_number >= quest_data['expires_at_round']:
                        game_state.public_announcements.append(f"{player.name} returned to the grave following the vote.")
                        kill_player(player_id, "Lazarus")
                        player.status_effects.pop('lazarus_effect', None)
                        broadcast_game_state()


        now = time.time(); phase = game_state.current_phase; sub_phase = game_state.voting_sub_phase; start_time = game_state.last_phase_start_time
        # REMOVED: The automatic advancement from Evening phase based on a timer.
        if (phase == "Voting" and sub_phase == "Nomination" and now - start_time >= VOTING_NOMINATION_TIMER_SECONDS):
            process_nominations()
        elif (phase == "Voting" and sub_phase == "Speaking" and game_state.current_speaker_index != -1 and now - start_time >= VOTING_SPEAKER_TIMER_SECONDS):
            game_state.current_speaker_index += 1
            start_next_speaker_turn()
        elif (phase == "Voting" and sub_phase == "Execution" and now - start_time >= VOTING_EXECUTION_TIMER_SECONDS):
            print("[TIMER] Execution vote is up.")
            resolve_execution_vote()
            game_state.advance_phase()
            broadcast_game_state()

@app.route('/')
def index():
    """Serve the main client page."""
    return render_template('index.html')

if __name__ == '__main__':
    reset_game()
    socketio.start_background_task(game_loop)
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask-SocketIO server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
