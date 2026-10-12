package cedhai;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import mage.abilities.ActivatedAbility;
import mage.abilities.Ability;
import mage.abilities.PlayLandAbility;
import mage.abilities.SpellAbility;
import mage.cards.Card;
import mage.cards.decks.Deck;
import mage.cards.decks.DeckCardLists;
import mage.cards.decks.importer.TxtDeckImporter;
import mage.cards.repository.CardScanner;
import mage.cards.repository.RepositoryUtil;
import mage.constants.*;
import mage.game.CommanderFreeForAll;
import mage.game.Game;
import mage.game.GameOptions;
import mage.game.mulligan.MulliganType;
import mage.game.permanent.Permanent;
import mage.game.stack.StackObject;
import mage.game.events.GameEvent;
import mage.game.combat.CombatGroup;
import mage.player.ai.ComputerPlayer;
import mage.players.Player;
import mage.util.RandomUtil;
import mage.filter.FilterMana;
import mage.watchers.common.CommanderInfoWatcher;
import org.apache.log4j.BasicConfigurator;
import org.apache.log4j.Level;
import org.apache.log4j.Logger;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** A narrow land/pass decision spike against unmodified XMage libraries. */
public final class BridgeMain {
    private static final Gson JSON = new Gson();
    private static final List<BridgePlayer> SEATS = new ArrayList<>();
    private static BufferedReader reader;
    private static BufferedWriter writer;
    private static String gameId;
    private static int decisions;
    private static int appliedLands;
    private static int castSpells;
    private static int resolvedSpells;
    private static int attacks;
    private static int blocks;
    private static boolean basicMode;
    private static final Set<String> SIMPLE_CREATURES = Set.of("Isamaru, Hound of Konda",
        "Savannah Lions", "Elite Vanguard", "Grizzly Bears", "Runeclaw Bear", "Yargle and Multani");
    private static final Map<UUID, String> CASTS = new LinkedHashMap<>();
    private static RuntimeException failure;

    private static Map<String, Object> fields(Object... pairs) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int i = 0; i < pairs.length; i += 2) {
            result.put((String) pairs[i], pairs[i + 1]);
        }
        return result;
    }

    private static List<Boolean> colors(Card card) {
        FilterMana color = card.getColorIdentity();
        return List.of(color.isWhite(), color.isBlue(), color.isBlack(), color.isRed(), color.isGreen());
    }

    private static JsonObject exchange(Map<String, Object> event) {
        try {
            writer.write(JSON.toJson(event));
            writer.newLine();
            writer.flush();
            String line = reader.readLine();
            if (line == null) throw new IOException("Python disconnected");
            JsonObject response = JSON.fromJson(line, JsonObject.class);
            if (response.has("error")) throw new IOException(response.get("error").getAsString());
            return response;
        } catch (Exception ex) {
            failure = new IllegalStateException("External policy exchange failed", ex);
            throw failure;
        }
    }

    private static int seat(UUID id) {
        for (BridgePlayer player : SEATS) if (player.getId().equals(id)) return player.seat;
        return -1;
    }

    private static Map<String, Object> publicState(Game game) {
        List<Object> players = new ArrayList<>();
        List<Object> commanders = new ArrayList<>();
        for (BridgePlayer original : SEATS) {
            Player player = game.getPlayer(original.getId());
            players.add(fields("seat", original.seat, "life", player.getLife(),
                "hand_count", player.getHand().size(), "library_count", player.getLibrary().size(),
                "battlefield_count", game.getBattlefield().getAllActivePermanents(player.getId()).size(),
                "in_game", player.isInGame(), "has_won", player.hasWon(), "has_lost", player.hasLost(),
                "has_drawn", player.hasDrew(), "mana_pool", player.getManaPool().getMana().toString()));
            for (UUID id : game.getCommandersIds(player, CommanderCardType.ANY, false)) {
                Card card = game.getCard(id);
                if (card == null) continue;
                List<Integer> damage = new ArrayList<>();
                CommanderInfoWatcher watcher = game.getState().getWatcher(CommanderInfoWatcher.class, id);
                for (BridgePlayer target : SEATS) {
                    damage.add(watcher == null ? 0 : watcher.getDamageToPlayer().getOrDefault(target.getId(), 0));
                }
                commanders.add(fields("owner_seat", original.seat, "name", card.getName(), "id", id.toString(),
                    "zone", game.getState().getZone(id), "damage_to_seats", damage,
                    "mana_value", card.getManaValue(), "power", card.getPower().getValue(),
                    "toughness", card.getToughness().getValue(), "colors", colors(card)));
            }
        }
        List<Object> battlefield = new ArrayList<>();
        for (Permanent permanent : game.getBattlefield().getAllActivePermanents()) {
            Map<String, Object> item = fields("id", permanent.getId().toString(),
                "controller_seat", seat(permanent.getControllerId()), "tapped", permanent.isTapped(),
                "face_down", permanent.isFaceDown(game));
            if (!permanent.isFaceDown(game)) {
                item.putAll(fields("name", permanent.getName(), "power", permanent.getPower().getValue(),
                    "toughness", permanent.getToughness().getValue(), "mana_value", permanent.getManaValue(),
                    "mana_cost", permanent.getManaCost().getText(), "colors", colors(permanent),
                    "creature", permanent.getCardType(game).contains(CardType.CREATURE),
                    "land", permanent.getCardType(game).contains(CardType.LAND)));
            }
            battlefield.add(item);
        }
        battlefield.sort(Comparator.comparing(item -> Objects.toString(((Map<?, ?>) item).get("name"), ""))
            .thenComparing(item -> ((Map<?, ?>) item).get("controller_seat").toString()));
        List<Object> stack = new ArrayList<>();
        for (StackObject object : game.getStack()) {
            // Basic mode only casts face-up vanilla creatures; expose their visible stack state.
            stack.add(fields("name", object.getName(), "controller_seat", seat(object.getControllerId())));
        }
        List<Object> combat = new ArrayList<>();
        for (CombatGroup group : game.getCombat().getGroups()) {
            combat.add(fields("defender_seat", seat(group.getDefenderId()),
                "attackers", group.getAttackers(), "blockers", group.getBlockers()));
        }
        return fields("turn", game.getState().getTurnNum(),
            "phase", game.getState().getTurn().getPhase().getType().name(),
            "active_seat", seat(game.getActivePlayerId()), "players", players,
            "battlefield", battlefield, "stack", stack, "combat", combat, "commanders", commanders);
    }

    private static void recordResolutions(Game game) {
        Iterator<Map.Entry<UUID, String>> iterator = CASTS.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<UUID, String> entry = iterator.next();
            if (game.getState().getZone(entry.getKey()) == Zone.BATTLEFIELD) {
                exchange(fields("event", "resolved", "schema_version", 2, "request_id", entry.getValue(),
                    "card_id", entry.getKey().toString(), "zone", "BATTLEFIELD",
                    "public_state", publicState(game)));
                resolvedSpells++;
                iterator.remove();
            }
        }
    }

    private static final class BridgePlayer extends ComputerPlayer {
        private final int seat;

        BridgePlayer(int seat) {
            super("PythonSeat" + seat, RangeOfInfluence.ALL);
            this.seat = seat;
        }

        BridgePlayer(BridgePlayer other) {
            super(other);
            this.seat = other.seat;
        }

        @Override
        public BridgePlayer copy() {
            return new BridgePlayer(this);
        }

        private String[] ask(Game game, String scope, List<Object> actions) {
            List<Object> hand = new ArrayList<>();
            for (Card card : getHand().getCards(game)) {
                hand.add(fields("id", card.getId().toString(), "name", card.getName(),
                    "mana_value", card.getManaValue(), "mana_cost", card.getManaCost().getText()));
            }
            hand.sort(Comparator.comparing(item -> ((Map<?, ?>) item).get("name").toString()));
            int step = decisions++;
            String requestId = gameId + ":" + step;
            Map<String, Object> observation = fields("game_id", gameId, "step", step, "seat", seat,
                "public_state", publicState(game), "private_state", fields("hand", hand), "legal_actions", actions);
            JsonObject response = exchange(fields("event", "decision", "schema_version", 2,
                "request_id", requestId, "scope", scope, "observation", observation));
            if (!requestId.equals(response.get("request_id").getAsString())) {
                failure = new IllegalStateException("Mismatched decision response");
                throw failure;
            }
            String selected = response.get("action_id").getAsString();
            boolean offered = actions.stream().anyMatch(item -> ((Map<?, ?>) item).get("id").equals(selected));
            if (!offered) {
                failure = new IllegalStateException("Python selected an unavailable action");
                throw failure;
            }
            return new String[]{requestId, selected};
        }

        private void combatApplied(Game game, String[] choice, Permanent creature) {
            exchange(fields("event", "applied", "schema_version", 2, "request_id", choice[0],
                "action_id", choice[1], "seat", seat, "card_id", creature.getId().toString(),
                "card_name", creature.getName(), "zone", choice[1].equals("skip") ? "NONE" : "BATTLEFIELD",
                "public_state", publicState(game)));
        }

        @Override
        public void selectAttackers(Game game, UUID attackingPlayerId) {
            if (!basicMode || game.isSimulation()) return;
            game.fireEvent(new GameEvent(GameEvent.EventType.DECLARE_ATTACKERS_STEP_PRE, null, null, attackingPlayerId));
            if (game.replaceEvent(GameEvent.getEvent(GameEvent.EventType.DECLARING_ATTACKERS, attackingPlayerId, attackingPlayerId))) return;
            List<Permanent> creatures = getAvailableAttackers(game);
            creatures.sort(Comparator.comparing(Permanent::getName).thenComparing(p -> p.getId().toString()));
            for (Permanent creature : creatures) {
                List<Object> actions = new ArrayList<>();
                actions.add(fields("id", "skip", "label", "Do not attack"));
                Map<String, UUID> targets = new LinkedHashMap<>();
                for (BridgePlayer other : SEATS) {
                    if (!other.getId().equals(getId()) && game.getCombat().getDefenders().contains(other.getId())
                            && game.getPlayer(other.getId()).isInGame() && creature.canAttack(other.getId(), game)) {
                        String id = "attack:" + other.seat;
                        targets.put(id, other.getId());
                        actions.add(fields("id", id, "label", "Attack seat " + other.seat + " with " + creature.getName(),
                            "features", fields("kind", "attack", "card_id", creature.getId().toString(),
                                "target_seat", other.seat, "power", creature.getPower().getValue(),
                                "toughness", creature.getToughness().getValue())));
                    }
                }
                String[] choice = ask(game, "attack", actions);
                if (!choice[1].equals("skip")) {
                    declareAttacker(creature.getId(), targets.get(choice[1]), game, false);
                    CombatGroup group = game.getCombat().findGroup(creature.getId());
                    if (group == null || !group.getDefenderId().equals(targets.get(choice[1]))) {
                        throw new IllegalStateException("Attacker declaration failed");
                    }
                    attacks++;
                }
                combatApplied(game, choice, creature);
            }
            game.getPlayers().resetPassed();
        }

        @Override
        public void selectBlockers(Ability source, Game game, UUID defendingPlayerId) {
            if (!basicMode || game.isSimulation()) return;
            game.fireEvent(new GameEvent(GameEvent.EventType.DECLARE_BLOCKERS_STEP_PRE, null, null, defendingPlayerId));
            if (game.replaceEvent(GameEvent.getEvent(GameEvent.EventType.DECLARING_BLOCKERS, defendingPlayerId, defendingPlayerId))) return;
            List<Permanent> creatures = getAvailableBlockers(game);
            creatures.sort(Comparator.comparing(Permanent::getName).thenComparing(p -> p.getId().toString()));
            for (Permanent creature : creatures) {
                List<Object> actions = new ArrayList<>();
                actions.add(fields("id", "skip", "label", "Do not block"));
                Map<String, UUID> targets = new LinkedHashMap<>();
                for (CombatGroup group : game.getCombat().getGroups()) {
                    if (!group.getDefenderId().equals(getId()) || !group.canBlock(creature, game)) continue;
                    for (UUID attacker : group.getAttackers()) {
                        if (!creature.canBlock(attacker, game)) continue;
                        String id = "block:" + targets.size();
                        Permanent target = game.getPermanent(attacker);
                        targets.put(id, attacker);
                        actions.add(fields("id", id, "label", "Block " + target.getName() + " with " + creature.getName(),
                            "features", fields("kind", "block", "card_id", creature.getId().toString(),
                                "target_seat", seat(target.getControllerId()), "power", creature.getPower().getValue(),
                                "toughness", creature.getToughness().getValue(), "target_power", target.getPower().getValue(),
                                "target_toughness", target.getToughness().getValue(), "target_mana_value", target.getManaValue())));
                    }
                }
                String[] choice = ask(game, "block", actions);
                if (!choice[1].equals("skip")) {
                    UUID attacker = targets.get(choice[1]);
                    declareBlocker(defendingPlayerId, creature.getId(), attacker, game, false);
                    if (!game.getCombat().findGroup(attacker).getBlockers().contains(creature.getId())) {
                        throw new IllegalStateException("Blocker declaration failed");
                    }
                    blocks++;
                }
                combatApplied(game, choice, creature);
            }
            game.getPlayers().resetPassed();
        }

        @Override
        public boolean priority(Game game) {
            if (game.isSimulation()) {
                pass(game);
                return false;
            }
            if (failure != null) throw failure;
            recordResolutions(game);
            List<ActivatedAbility> lands = new ArrayList<>();
            for (ActivatedAbility ability : getPlayable(game, true)) {
                // Restrict the spike to own-hand lands. XMage supplies timing/restriction checks.
                boolean land = ability instanceof PlayLandAbility && getHand().contains(ability.getSourceId());
                boolean spell = basicMode && ability instanceof SpellAbility
                    && SIMPLE_CREATURES.contains(game.getCard(ability.getSourceId()).getName());
                if ((land || spell) && ability.canActivate(getId(), game).canActivate()) lands.add(ability);
            }
            lands.sort(Comparator.comparing((ActivatedAbility a) -> game.getCard(a.getSourceId()).getName())
                .thenComparing(a -> a.getSourceId().toString()));
            List<Object> actions = new ArrayList<>();
            actions.add(fields("id", "pass", "label", "Pass priority"));
            for (int i = 0; i < lands.size(); i++) {
                Card card = game.getCard(lands.get(i).getSourceId());
                boolean land = lands.get(i) instanceof PlayLandAbility;
                actions.add(fields("id", (land ? "land:" : "cast:") + i,
                    "label", (land ? "Play " : "Cast ") + card.getName(),
                    "features", fields("kind", land ? "land" : "cast", "card_id", card.getId().toString(),
                        "mana_value", card.getManaValue(), "colors", colors(card), "power", card.getPower().getValue(),
                        "toughness", card.getToughness().getValue())));
            }
            String[] choice = ask(game, basicMode ? "priority_basic" : "own_hand_land_or_pass", actions);
            String requestId = choice[0];
            String selected = choice[1];
            boolean result;
            String cardName = "";
            String cardId = "";
            if (selected.equals("pass")) {
                pass(game);
                result = false;
            } else {
                int index = -1;
                for (int i = 0; i < lands.size(); i++) {
                    String prefix = lands.get(i) instanceof PlayLandAbility ? "land:" : "cast:";
                    if (selected.equals(prefix + i)) index = i;
                }
                if (index < 0) {
                    failure = new IllegalStateException("Python selected an unavailable action");
                    throw failure;
                }
                ActivatedAbility ability = lands.get(index);
                cardName = game.getCard(ability.getSourceId()).getName();
                cardId = ability.getSourceId().toString();
                result = activateAbility(ability, game);
                Zone expected = ability instanceof PlayLandAbility ? Zone.BATTLEFIELD : Zone.STACK;
                if (!result || game.getState().getZone(ability.getSourceId()) != expected) {
                    failure = new IllegalStateException("Selected action did not reach expected zone " + expected);
                    throw failure;
                }
                if (ability instanceof PlayLandAbility) appliedLands++;
                else {
                    castSpells++;
                    CASTS.put(ability.getSourceId(), requestId);
                }
            }
            exchange(fields("event", "applied", "schema_version", 2, "request_id", requestId,
                "action_id", selected, "seat", seat, "card_name", cardName, "card_id", cardId,
                "zone", selected.equals("pass") ? "NONE" : selected.startsWith("cast:") ? "STACK" : "BATTLEFIELD",
                "public_state", publicState(game)));
            return result;
        }
    }

    public static void main(String[] args) {
        int exit = 1;
        BasicConfigurator.configure();
        Logger.getRootLogger().setLevel(Level.WARN);
        try (Socket socket = new Socket()) {
            // The listener is loopback-only; policy failure never falls back to native priority AI.
            socket.connect(new InetSocketAddress("127.0.0.1", Integer.parseInt(args[0])), 10000);
            socket.setSoTimeout(10000);
            reader = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
            writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8));
            long seed = Long.parseLong(args[1]);
            int maxTurns = Integer.parseInt(args[2]);
            basicMode = args.length > 7 && args[7].equals("basic");
            gameId = "xmage-" + seed;
            System.out.println("Bootstrapping XMage card database...");
            RepositoryUtil.bootstrapLocalDb();
            CardScanner.scan();
            RandomUtil.setSeed(seed);
            CommanderFreeForAll game = new CommanderFreeForAll(MultiplayerAttackOption.MULTIPLE,
                RangeOfInfluence.ALL, MulliganType.LONDON.getMulligan(1), 40, 7);
            game.setLocalRandom(new Random(seed));
            game.setNumPlayers(4);
            List<Deck> decks = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                StringBuilder errors = new StringBuilder();
                DeckCardLists lists = new TxtDeckImporter(true).importDeck(args[3 + i], errors, false);
                if (!errors.isEmpty()) throw new IllegalArgumentException(errors.toString());
                Deck deck = Deck.load(lists, false, false);
                mage.deck.Commander validator = new mage.deck.Commander();
                if (!validator.validate(deck)) throw new IllegalArgumentException(validator.getErrorsListInfo());
                if (basicMode) {
                    Set<Card> curriculumCards = new HashSet<>(deck.getCards());
                    curriculumCards.addAll(deck.getSideboard());
                    for (Card card : curriculumCards) {
                        if (!card.isBasic() && !SIMPLE_CREATURES.contains(card.getName())) {
                            throw new IllegalArgumentException("Unsupported curriculum card: " + card.getName());
                        }
                    }
                }
                BridgePlayer player = new BridgePlayer(i);
                SEATS.add(player);
                decks.add(deck);
                game.loadCards(deck.getCards(), player.getId());
                game.loadCards(deck.getSideboard(), player.getId());
                System.out.println("Validated seat " + i + ": " + deck.getCards().size() + " main, "
                    + deck.getSideboard().size() + " commanders");
            }
            // XMage constructs turn lists by inserting each registered player at index zero.
            for (int i = SEATS.size() - 1; i >= 0; i--) {
                game.addPlayer(SEATS.get(i), decks.get(i));
            }
            GameOptions options = new GameOptions();
            options.testMode = false;
            options.stopOnTurn = maxTurns;
            options.stopAtStep = PhaseStep.END_TURN;
            game.setGameOptions(options);
            game.setStartingPlayerId(SEATS.get(0).getId());
            System.out.println("Starting four-player Commander game...");
            game.start(null);
            recordResolutions(game);
            if (failure != null) throw failure;
            if (decisions == 0) throw new IllegalStateException("No external decisions occurred");
            boolean truncated = game.isPaused();
            List<Integer> winners = new ArrayList<>();
            for (BridgePlayer player : SEATS) if (game.getPlayer(player.getId()).hasWon()) winners.add(player.seat);
            List<Double> rewards = new ArrayList<>();
            for (int i = 0; i < 4; i++) rewards.add(winners.contains(i) ? 1.0 : 0.0);
            exchange(fields("event", "finished", "schema_version", 2, "game_id", gameId,
                "decisions", decisions, "applied_lands", appliedLands, "truncated", truncated,
                "cast_spells", castSpells, "resolved_spells", resolvedSpells,
                "attacks", attacks, "blocks", blocks, "rewards", truncated ? null : rewards,
                "terminal", !truncated && game.checkIfGameIsOver(), "winners", winners,
                "public_state", publicState(game)));
            System.out.println("Bridge completed: " + decisions + " decisions, " + appliedLands + " land plays");
            exit = 0;
        } catch (Throwable ex) {
            ex.printStackTrace();
        }
        System.exit(exit);
    }
}
