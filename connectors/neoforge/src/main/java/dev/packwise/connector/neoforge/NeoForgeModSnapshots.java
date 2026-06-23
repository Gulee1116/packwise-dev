package dev.packwise.connector.neoforge;

import dev.packwise.connector.protocol.ModSnapshot;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;

public final class NeoForgeModSnapshots {
    private NeoForgeModSnapshots() {
    }

    public static List<ModSnapshot> collectLoadedMods() {
        try {
            Class<?> modListClass = Class.forName("net.neoforged.fml.ModList");
            Object modList = modListClass.getMethod("get").invoke(null);
            Object modInfos = modList.getClass().getMethod("getMods").invoke(modList);
            if (!(modInfos instanceof Collection<?> collection)) {
                throw new IllegalStateException("NeoForge ModList#getMods did not return a collection");
            }
            return fromModInfoObjects(collection);
        } catch (ClassNotFoundException error) {
            throw new IllegalStateException("NeoForge ModList is not available in this runtime", error);
        } catch (NoSuchMethodException | IllegalAccessException | InvocationTargetException error) {
            throw new IllegalStateException("Failed to read NeoForge ModList through reflection", error);
        }
    }

    public static List<ModSnapshot> fromModInfoObjects(Collection<?> modInfos) {
        List<ModSnapshot> snapshots = new ArrayList<>();
        for (Object modInfo : modInfos) {
            snapshots.add(new ModSnapshot(
                    invokeString(modInfo, "getModId"),
                    invokeString(modInfo, "getDisplayName"),
                    invokeToString(modInfo, "getVersion"),
                    "neoforge:ModList"));
        }
        snapshots.sort(Comparator.comparing(ModSnapshot::modId));
        return List.copyOf(snapshots);
    }

    private static String invokeString(Object target, String methodName) {
        Object value = invoke(target, methodName);
        if (!(value instanceof String text)) {
            throw new IllegalStateException(methodName + " did not return a string");
        }
        return text;
    }

    private static String invokeToString(Object target, String methodName) {
        Object value = invoke(target, methodName);
        return String.valueOf(value);
    }

    private static Object invoke(Object target, String methodName) {
        try {
            Method method = target.getClass().getMethod(methodName);
            return method.invoke(target);
        } catch (NoSuchMethodException | IllegalAccessException | InvocationTargetException error) {
            throw new IllegalStateException("Failed to invoke " + methodName + " on " + target.getClass().getName(), error);
        }
    }
}
