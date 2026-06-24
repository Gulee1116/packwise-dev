package dev.packwise.connector.protocol;

public final class RuntimeSectionNames {
    public static final String MODS = "mods";
    public static final String ITEMS = "items";
    public static final String BLOCKS = "blocks";
    public static final String FLUIDS = "fluids";
    public static final String TAGS = "tags";
    public static final String RECIPES = "recipes";
    public static final String ADVANCEMENTS = "advancements";
    public static final String FTB_QUESTS = "ftb_quests";
    public static final String PLAYER_PROGRESS = "player_progress";
    public static final String TEAM_PROGRESS = "team_progress";
    public static final String STAGES = "stages";

    private RuntimeSectionNames() {
    }

    public static boolean isStandard(String sectionName) {
        return switch (sectionName) {
            case MODS, ITEMS, BLOCKS, FLUIDS, TAGS, RECIPES, ADVANCEMENTS,
                    FTB_QUESTS, PLAYER_PROGRESS, TEAM_PROGRESS, STAGES -> true;
            default -> false;
        };
    }
}
