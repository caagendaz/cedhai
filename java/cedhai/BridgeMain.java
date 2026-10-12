package cedhai;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import mage.abilities.ActivatedAbility;
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
import mage.player.ai.ComputerPlayer;
import mage.players.Player;
import mage.util.RandomUtil;
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
        for (BridgePlayer original : SEATS) {
            Player player = game.getPlayer(original.getId());
            players.add(fields("seat", original.seat, "life", player.getLife(),
                "hand_count", player.getHand().size(), "library_count", player.getLibrary().size(),
                "battlefield_count", game.getBattlefield().getAllActivePermanents(player.getId()).size(),
                "in_game", player.isInGame(), "mana_pool", player.getManaPool().getMana().toString()));
        }
        List<Object> battlefield = new ArrayList<>();
        for (Permanent permanent : game.getBattlefield().getAllActivePermanents()) {
            Map<String, Object> item = fields("id", permanent.getId().toString(),
                "controller_seat", seat(permanent.getControllerId()), "tapped", permanent.isTapped(),
                "face_down", permanent.isFaceDown(game));
            if (!permanent.isFaceDown(game)) {
                item.putAll(fields("name", permanent.getName(), "power", permanent.getPower().getValue(),
                    "toughness", permanent.getToughness().getValue(), "mana_value", permanent.getManaValue(),
                    "mana_cost", permanent.getManaCost().getText()));
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
        return fields("turn", game.getState().getTurnNum(),
            "phase", game.getState().getTurn().getPhase().getType().name(),
            "active_seat", seat(game.getActivePlayerId()), "players", players,
            "battlefield", battlefield, "stack", stack);
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
                        "mana_value", card.getManaValue(), "power", card.getPower().getValue(),
                        "toughness", card.getToughness().getValue())));
            }
            List<Object> hand = new ArrayList<>();
            for (Card card : getHand().getCards(game)) {
                hand.add(fields("id", card.getId().toString(), "name", card.getName(),
                    "mana_value", card.getManaValue(), "mana_cost", card.getManaCost().getText()));
            }
            hand.sort(Comparator.comparing(item -> ((Map<?, ?>) item).get("name").toString()));
            int step = decisions++;
            String requestId = gameId + ":" + step;
            Map<String, Object> observation = fields("game_id", gameId, "step", step, "seat", seat,
                "public_state", publicState(game), "private_state", fields("hand", hand),
                "legal_actions", actions);
            JsonObject response = exchange(fields("event", "decision", "schema_version", 2,
                "request_id", requestId, "scope", basicMode ? "priority_basic" : "own_hand_land_or_pass",
                "observation", observation));
            if (!requestId.equals(response.get("request_id").getAsString())) {
                failure = new IllegalStateException("Mismatched decision response");
                throw failure;
            }
            String selected = response.get("action_id").getAsString();
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
            exchange(fields("event", "finished", "schema_version", 2, "game_id", gameId,
                "decisions", decisions, "applied_lands", appliedLands, "truncated", truncated,
                "cast_spells", castSpells, "resolved_spells", resolvedSpells,
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
