package dev.packwise.connector.protocol;

public final class AgentAnswerTest {
    public static void main(String[] args) {
        parsesAnswerPacketSummary();
        parsesNextStepsWithBrackets();
        parsesSourceRefs();
        System.out.println("AgentAnswerTest passed");
    }

    private static void parsesAnswerPacketSummary() {
        AgentAnswer answer = AgentAnswer.fromAnswerPacketJson(
                "{\"answer\":{\"summary\":\"找到 2 条配方\",\"next_steps\":[\"看 runtime recipes\",\"检查任务\"],\"confidence\":\"medium\"}}");

        assertEquals("找到 2 条配方", answer.summary(), "summary");
        assertEquals(2, answer.nextSteps().size(), "next step count");
        assertEquals("medium", answer.confidence(), "confidence");
    }

    private static void parsesNextStepsWithBrackets() {
        AgentAnswer answer = AgentAnswer.fromAnswerPacketJson(
                "{\"answer\":{\"summary\":\"按服务器 runtime 为准\",\"next_steps\":[\"检查 tag [forge:stone]\", \"确认 recipes/tags\"],\"confidence\":\"medium\"}}");

        assertEquals(2, answer.nextSteps().size(), "next step count");
        assertEquals("检查 tag [forge:stone]", answer.nextSteps().get(0), "bracket next step");
    }

    private static void parsesSourceRefs() {
        AgentAnswer answer = AgentAnswer.fromAnswerPacketJson(
                "{\"answer\":{\"summary\":\"找到 1 条配方\",\"next_steps\":[],\"source_refs\":[{\"kind\":\"runtime_dump_section\",\"path\":\"dump_1/recipes\",\"label\":\"Runtime recipes\"},{\"kind\":\"recipe\",\"path\":\"minecraft:stonecutting/stone\",\"label\":\"minecraft:stone\"}],\"confidence\":\"medium\"}}");

        assertEquals(2, answer.sourceRefs().size(), "source ref count");
        assertEquals("runtime_dump_section", answer.sourceRefs().get(0).kind(), "first ref kind");
        assertEquals("dump_1/recipes", answer.sourceRefs().get(0).path(), "first ref path");
        assertEquals("runtime_dump_section:dump_1/recipes", answer.sourceRefs().get(0).compact(), "first compact ref");
        assertEquals("recipe:minecraft:stonecutting/stone", answer.sourceRefs().get(1).compact(), "second compact ref");
    }

    private static void assertEquals(Object expected, Object actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + " but got " + actual);
        }
    }
}
