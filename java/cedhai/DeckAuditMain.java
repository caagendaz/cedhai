package cedhai;

import com.google.gson.Gson;
import mage.cards.decks.Deck;
import mage.cards.decks.DeckCardLists;
import mage.cards.decks.importer.TxtDeckImporter;
import mage.cards.repository.CardScanner;
import mage.cards.repository.RepositoryUtil;
import org.apache.log4j.BasicConfigurator;
import org.apache.log4j.Level;
import org.apache.log4j.Logger;
import java.nio.file.*;
import java.util.*;

/** Validate deck loading against the installed engine's actual card implementations. */
public final class DeckAuditMain {
    public static void main(String[] args) throws Exception {
        BasicConfigurator.configure();
        Logger.getRootLogger().setLevel(Level.WARN);
        RepositoryUtil.bootstrapLocalDb();
        CardScanner.scan();
        List<Object> reports = new ArrayList<>();
        for (int index = 1; index < args.length; index++) {
            Map<String, Object> report = new LinkedHashMap<>();
            report.put("path", args[index]);
            StringBuilder errors = new StringBuilder();
            DeckCardLists lists = new TxtDeckImporter(true).importDeck(args[index], errors, false);
            report.put("import_messages", errors.toString());
            try {
                Deck deck = Deck.load(lists, false, false);
                mage.deck.Commander validator = new mage.deck.Commander();
                boolean legal = validator.validate(deck);
                report.put("main_loaded", deck.getCards().size());
                report.put("commanders_loaded", deck.getSideboard().size());
                report.put("validation_messages", validator.getErrorsListInfo());
                report.put("engine_ready", legal && errors.isEmpty());
            } catch (Exception ex) {
                report.put("engine_ready", false);
                report.put("load_error", ex.toString());
            }
            reports.add(report);
        }
        Files.writeString(Path.of(args[0]), new Gson().toJson(reports));
        System.exit(0);
    }
}
