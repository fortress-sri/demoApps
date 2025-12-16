import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.io.StringWriter;

// WikiText core
//   org.eclipse.mylyn.wikitext_3.0.48.202308291007.jar
// Markup language support
//   org.eclipse.mylyn.wikitext.markdown_3.0.48.202308291007.jar
//   org.eclipse.mylyn.wikitext.textile_3.0.48.202308291007.jar
// Guava: Google Core Libraries for Java
//   guava-33.5.0-jre.jar

import org.eclipse.mylyn.wikitext.parser.MarkupParser;
import org.eclipse.mylyn.wikitext.parser.builder.HtmlDocumentBuilder;
import org.eclipse.mylyn.wikitext.parser.markup.MarkupLanguage;
import org.eclipse.mylyn.wikitext.util.ServiceLocator;

public final class WikiTextToHtmlConverter {

    private WikiTextToHtmlConverter() {
        // Utility class, no instantiation
    }

    /**
     * Converts a given WikiText string (e.g., Textile, Markdown, etc.) to HTML.
     *
     * @param markupLanguageName The name of the markup language (e.g., "Textile").
     * @param wikiText The WikiText content to convert.
     * @return The converted HTML string.
     */
    public static String convertWikiTextToHtml(String markupLanguageName, String wikiText) {
        MarkupLanguage language = ServiceLocator.getInstance().getMarkupLanguage(markupLanguageName);
        if (language == null) {
            throw new IllegalArgumentException("Unsupported markup language: " + markupLanguageName);
        }

        StringWriter writer = new StringWriter();
        HtmlDocumentBuilder builder = new HtmlDocumentBuilder(writer);
        MarkupParser parser = new MarkupParser(language, builder);
        parser.parse(wikiText);
        return writer.toString();
    }

    public static void main(String[] args) {
    	String content = "";

    	try {
	    	String line;

	        BufferedReader bufferreader = new BufferedReader(new FileReader(args[0]));

	        while ((line = bufferreader.readLine()) != null) {  
	        	content += line + "\n";
	        }

	        bufferreader.close ();
	    } catch (FileNotFoundException ex) {
	        ex.printStackTrace();
	    } catch (IOException ex) {
	        ex.printStackTrace();
	    }

        String htmlOutput = convertWikiTextToHtml("Markdown", content);
        System.out.println(htmlOutput);
    }
}
